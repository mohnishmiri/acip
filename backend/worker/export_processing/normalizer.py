"""Row normalisation (versioned).

Bump ``NORMALIZER_VERSION`` whenever the output of ``normalise_row`` changes so records
can be traced to the logic that produced them and reprocessed deliberately.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from worker.export_processing.schema import SchemaMapping

NORMALIZER_VERSION = "2026.11.1"


class RowError(ValueError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


_RG_RE = re.compile(r"/resourcegroups/([^/]+)", re.IGNORECASE)
_PROVIDER_RE = re.compile(r"/providers/(.+)$", re.IGNORECASE)
_SUB_RE = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def parse_date(value: str) -> date:
    v = (value or "").strip()
    if not v:
        raise RowError("invalid_date", "empty date")
    try:
        if "/" in v:  # Azure CSV exports use MM/DD/YYYY
            m, d, y = v.split(" ")[0].split("/")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(v[:10])
    except (ValueError, TypeError) as exc:
        raise RowError("invalid_date", f"unparseable date '{v}'") from exc


def parse_decimal(value: str | None, *, field_name: str, required: bool = False) -> Decimal | None:
    v = (value or "").strip()
    if not v:
        if required:
            raise RowError("invalid_number", f"empty {field_name}")
        return None
    try:
        d = Decimal(v.replace(",", "")) if v.count(",") and "." in v else Decimal(v)
    except InvalidOperation as exc:
        raise RowError("invalid_number", f"unparseable {field_name} '{v}'") from exc
    if not d.is_finite():
        raise RowError("invalid_number", f"non-finite {field_name} '{v}'")
    return d


def parse_tags(value: str | None) -> dict[str, str] | None:
    v = (value or "").strip()
    if not v:
        return None
    if not v.startswith("{"):
        v = "{" + v + "}"  # legacy format: "key": "value","key2": "value2"
    try:
        parsed = json.loads(v)
    except json.JSONDecodeError:
        # last resort: key:value pairs separated by commas
        out: dict[str, str] = {}
        for part in v.strip("{}").split(","):
            if ":" in part:
                k, _, val = part.partition(":")
                out[k.strip().strip('"')] = val.strip().strip('"')
        return out or None
    if isinstance(parsed, dict):
        return {str(k): ("" if val is None else str(val)) for k, val in parsed.items()}
    return None


def parse_json_obj(value: str | None) -> dict[str, Any] | None:
    v = (value or "").strip()
    if not v or not v.startswith("{"):
        return None
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def normalise_region(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower().replace(" ", "")
    return v or None


def resource_type_from_id(resource_id: str) -> str | None:
    m = _PROVIDER_RE.search(resource_id)
    if not m:
        return None
    parts = [p for p in m.group(1).split("/") if p]
    if len(parts) < 2:
        return None
    namespace = parts[0]
    types = parts[1::2]  # providers/NS/type/name/subtype/subname -> type, subtype
    return (namespace + "/" + "/".join(types)).lower()


@dataclass
class RunContext:
    subscription_fk: int
    subscription_guid: str
    dataset_type: str
    default_currency: str
    export_run_id: int
    ingestion_file_id: int
    is_demo: bool


def _get(raw: dict[str, str], mapping: SchemaMapping, fname: str) -> str | None:
    col = mapping.field_to_column.get(fname)
    if col is None:
        return None
    v = raw.get(col)
    if v is None:
        return None
    v = v.strip()
    return v or None


def normalise_row(raw: dict[str, str], mapping: SchemaMapping, ctx: RunContext, row_number: int) -> dict[str, Any]:
    usage_date = parse_date(_get(raw, mapping, "usage_date") or "")
    cost = parse_decimal(_get(raw, mapping, "cost"), field_name="cost", required=True)

    sub_raw = _get(raw, mapping, "subscription_id")
    if sub_raw:
        m = _SUB_RE.search(sub_raw)
        sub_guid = (m.group(1) if m else sub_raw).lower()
        if sub_guid != ctx.subscription_guid.lower():
            raise RowError("subscription_mismatch", f"row subscription {sub_guid} does not match export scope {ctx.subscription_guid}")

    resource_id = _get(raw, mapping, "resource_id")
    resource_key = resource_id.lower() if resource_id else ""
    resource_group = _get(raw, mapping, "resource_group")
    if not resource_group and resource_id:
        m = _RG_RE.search(resource_id)
        resource_group = m.group(1) if m else None
    resource_name = _get(raw, mapping, "resource_name") or (resource_id.rstrip("/").rsplit("/", 1)[-1] if resource_id else None)
    resource_type = _get(raw, mapping, "resource_type")
    resource_type = resource_type.lower() if resource_type else (resource_type_from_id(resource_id) if resource_id else None)

    additional_info = parse_json_obj(_get(raw, mapping, "additional_info"))
    meter_category = _get(raw, mapping, "meter_category")
    meter_subcategory = _get(raw, mapping, "meter_subcategory")
    sku = None
    if additional_info:
        sku = additional_info.get("ServiceType") or additional_info.get("VMSize") or additional_info.get("SkuName")
    sku = sku or _get(raw, mapping, "sku_column") or meter_subcategory

    tags = parse_tags(_get(raw, mapping, "tags"))
    currency = (_get(raw, mapping, "billing_currency") or ctx.default_currency).upper()[:3]

    extra = {}
    for col in mapping.unmapped_columns:
        v = raw.get(col)
        if v not in (None, ""):
            extra[col] = v[:500]

    return {
        "usage_date": usage_date,
        "dataset_type": ctx.dataset_type,
        "billing_currency": currency,
        "subscription_fk": ctx.subscription_fk,
        "export_run_id": ctx.export_run_id,
        "ingestion_file_id": ctx.ingestion_file_id,
        "source_row_number": row_number,
        "billing_period_start": _opt_date(_get(raw, mapping, "billing_period_start")),
        "billing_period_end": _opt_date(_get(raw, mapping, "billing_period_end")),
        "cost": cost,
        "cost_usd": parse_decimal(_get(raw, mapping, "cost_usd"), field_name="cost_usd"),
        "payg_cost": parse_decimal(_get(raw, mapping, "payg_cost"), field_name="payg_cost"),
        "quantity": parse_decimal(_get(raw, mapping, "quantity"), field_name="quantity"),
        "unit_of_measure": _get(raw, mapping, "unit_of_measure"),
        "unit_price": parse_decimal(_get(raw, mapping, "unit_price"), field_name="unit_price"),
        "effective_price": parse_decimal(_get(raw, mapping, "effective_price"), field_name="effective_price"),
        "resource_id": resource_id,
        "resource_key": resource_key,
        "resource_name": resource_name,
        "resource_group": resource_group.lower() if resource_group else None,
        "resource_type": resource_type,
        "region": normalise_region(_get(raw, mapping, "region")),
        "service_name": _get(raw, mapping, "service_name") or meter_category,
        "service_family": _get(raw, mapping, "service_family"),
        "consumed_service": _get(raw, mapping, "consumed_service"),
        "meter_id": _get(raw, mapping, "meter_id"),
        "meter_name": _get(raw, mapping, "meter_name"),
        "meter_category": meter_category,
        "meter_subcategory": meter_subcategory,
        "meter_region": _get(raw, mapping, "meter_region"),
        "product_name": _get(raw, mapping, "product_name"),
        "sku": sku,
        "charge_type": _get(raw, mapping, "charge_type") or "Usage",
        "pricing_model": _get(raw, mapping, "pricing_model") or "OnDemand",
        "frequency": _get(raw, mapping, "frequency"),
        "benefit_id": _get(raw, mapping, "benefit_id"),
        "benefit_name": _get(raw, mapping, "benefit_name"),
        "publisher_type": _get(raw, mapping, "publisher_type"),
        "tags": tags,
        "additional_info": additional_info,
        "extra": extra or None,
        "cost_center_column": _get(raw, mapping, "cost_center_column"),
        "is_demo": ctx.is_demo,
        "normalizer_version": NORMALIZER_VERSION,
    }


def _opt_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return parse_date(v)
    except RowError:
        return None


def parse_iso_datetime(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
