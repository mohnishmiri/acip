"""Human-readable keys and labels for grouped dimensions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, AzureSubscription, Environment
from app.repositories.cost_repository import NONE_TOKEN

NONE_LABELS = {
    "owner": "Untagged (no owner)",
    "cost_center": "Untagged (no cost center)",
    "tag": "(tag not set)",
    "region": "(no region)",
    "resource_group": "(no resource group)",
    "resource_type": "(no resource type)",
    "meter_category": "(no meter category)",
    "meter_name": "(no meter)",
    "sku": "(no SKU)",
    "charge_type": "(none)",
    "pricing_model": "(none)",
}


class LabelResolver:
    def __init__(self, db: Session):
        self.apps = {a.id: a for a in db.execute(select(Application)).scalars()}
        self.envs = {e.id: e for e in db.execute(select(Environment)).scalars()}
        self.env_by_code = {e.code: e for e in self.envs.values()}
        self.subs = {s.id: s for s in db.execute(select(AzureSubscription)).scalars()}
        self.sub_by_guid = {s.subscription_id.lower(): s for s in self.subs.values()}

    def application(self, app_id: int | None, allocation_status: str | None = None) -> tuple[str, str]:
        if app_id is not None and app_id in self.apps:
            return str(app_id), self.apps[app_id].name
        if allocation_status == "shared":
            return "shared", "Shared Services"
        return "unallocated", "Unallocated"

    def environment(self, env_id: int | None) -> tuple[str, str]:
        if env_id is not None and env_id in self.envs:
            e = self.envs[env_id]
            return e.code, e.name
        return "unallocated", "Unallocated"

    def subscription(self, sub_fk: int | None) -> tuple[str, str]:
        s = self.subs.get(sub_fk) if sub_fk is not None else None
        if s is None:
            return str(sub_fk), f"Subscription {sub_fk}"
        return s.subscription_id, s.subscription_name

    def key_label(self, dim: str, values: dict[str, Any], label_hint: str | None = None) -> tuple[str, str]:
        if dim == "application":
            return self.application(values.get("application_id"), values.get("allocation_status"))
        if dim == "environment":
            return self.environment(values.get("environment_id"))
        if dim == "subscription":
            return self.subscription(values.get("subscription_fk"))
        if dim == "resource":
            key = values.get("resource_key") or ""
            if not key:
                return "", "(non-resource charges)"
            return key, label_hint or key.rstrip("/").rsplit("/", 1)[-1]
        if dim == "meter":
            sub, name = values.get("meter_subcategory"), values.get("meter_name")
            if not name and not sub:
                return NONE_TOKEN, NONE_LABELS["meter_name"]
            return f"{sub or ''}|{name or ''}", (f"{name} · {sub}" if sub and name else (name or sub))
        if dim == "tag":
            v = values.get("tag_value")
            return (v, v) if v else (NONE_TOKEN, NONE_LABELS["tag"])
        col = {"currency": "billing_currency", "unit": "unit_of_measure"}.get(dim, dim)
        v = values.get(col)
        if v is None or v == "":
            return NONE_TOKEN, NONE_LABELS.get(dim, "(none)")
        return str(v), str(v)

    def describe_resource_attrs(self, extra: dict[str, Any]) -> dict[str, Any]:
        out = dict(extra)
        if "subscription_fk" in extra:
            out["subscription_id"], out["subscription_name"] = self.subscription(extra["subscription_fk"])
        if "application_id" in extra or "allocation_status" in extra:
            out["application_key"], out["application_name"] = self.application(extra.get("application_id"), extra.get("allocation_status"))
        if "environment_id" in extra:
            out["environment_code"], out["environment_name"] = self.environment(extra.get("environment_id"))
        return out
