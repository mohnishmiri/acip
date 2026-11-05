"""Schema detection and column mapping for Azure Cost Management export files.

Azure export schemas differ by agreement type (EA / MCA / MOSP / CSP), dataset
(ActualCost / AmortizedCost / FOCUS) and API version, and column casing changes between
versions (``CostInBillingCurrency`` vs ``costInBillingCurrency``). Columns are matched on a
normalised name (lower-case, alphanumerics only) against an alias list so new or
re-cased columns do not break ingestion. Columns that are not mapped are preserved in
``cost_records.extra`` and the original header list is stored per file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# canonical field -> accepted normalised source column names (first present wins)
FIELD_ALIASES: dict[str, list[str]] = {
    "usage_date": ["date", "usagedate", "chargeperiodstart"],
    "billing_period_start": ["billingperiodstartdate", "billingperiodstart"],
    "billing_period_end": ["billingperiodenddate", "billingperiodend"],
    "subscription_id": ["subscriptionid", "subscriptionguid", "subaccountid"],
    "subscription_name": ["subscriptionname", "subaccountname"],
    "resource_group": ["resourcegroup", "resourcegroupname", "xresourcegroupname"],
    "resource_id": ["resourceid", "instanceid"],
    "resource_name": ["resourcename"],
    "resource_type": ["resourcetype", "xresourcetype"],
    "region": ["resourcelocation", "regionname", "location", "regionid"],
    "service_name": ["servicename"],
    "service_family": ["servicefamily", "servicecategory"],
    "consumed_service": ["consumedservice"],
    "meter_id": ["meterid"],
    "meter_name": ["metername"],
    "meter_category": ["metercategory"],
    "meter_subcategory": ["metersubcategory"],
    "meter_region": ["meterregion"],
    "product_name": ["productname", "product"],
    "quantity": ["quantity", "usagequantity", "consumedquantity"],
    "unit_of_measure": ["unitofmeasure", "consumedunit", "pricingunit"],
    "unit_price": ["unitprice", "listunitprice"],
    "effective_price": ["effectiveprice", "contractedunitprice"],
    "billing_currency": ["billingcurrency", "billingcurrencycode", "currency"],
    "cost": ["costinbillingcurrency", "cost", "pretaxcost"],
    "focus_billed_cost": ["billedcost"],
    "focus_effective_cost": ["effectivecost"],
    "cost_usd": ["costinusd"],
    "payg_cost": ["paygcostinbillingcurrency"],
    "charge_type": ["chargetype", "chargecategory"],
    "pricing_model": ["pricingmodel", "pricingcategory"],
    "frequency": ["frequency", "chargefrequency"],
    "benefit_id": ["benefitid", "reservationid", "commitmentdiscountid"],
    "benefit_name": ["benefitname", "reservationname", "commitmentdiscountname"],
    "publisher_type": ["publishertype"],
    "tags": ["tags"],
    "additional_info": ["additionalinfo", "xskudetails"],
    "cost_center_column": ["costcenter"],
    "sku_column": ["skuname", "xskumetersubcategory", "skuid"],
}

REQUIRED_FIELDS = ["usage_date"]  # plus one of the cost columns, validated separately

_norm_re = re.compile(r"[^a-z0-9]")


def normalise_header(name: str) -> str:
    return _norm_re.sub("", name.strip().lstrip("﻿").lower())


@dataclass
class SchemaMapping:
    source_columns: list[str]
    field_to_column: dict[str, str]
    unmapped_columns: list[str]
    detected_schema: str
    missing_required: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"fields": self.field_to_column, "unmapped": self.unmapped_columns, "detected_schema": self.detected_schema}


def detect_schema(normalised: set[str]) -> str:
    if {"billedcost", "effectivecost", "chargeperiodstart"} <= normalised:
        return "focus"
    if "costinbillingcurrency" in normalised:
        return "modern_actual_amortized"  # EA / MCA exports (2019-11-01+ schemas)
    if "pretaxcost" in normalised:
        return "legacy_pretax"
    if "cost" in normalised and "subscriptionguid" in normalised:
        return "ea_legacy"
    return "unknown"


def build_mapping(headers: list[str], dataset_type: str) -> SchemaMapping:
    by_norm: dict[str, str] = {}
    for h in headers:
        by_norm.setdefault(normalise_header(h), h)
    normalised = set(by_norm)
    schema = detect_schema(normalised)

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for fname, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in by_norm and by_norm[alias] not in used:
                mapping[fname] = by_norm[alias]
                used.add(by_norm[alias])
                break

    # FOCUS: the dataset decides which cost column is authoritative.
    if schema == "focus":
        if dataset_type == "amortized" and "focus_effective_cost" in mapping:
            mapping["cost"] = mapping["focus_effective_cost"]
        elif "focus_billed_cost" in mapping:
            mapping["cost"] = mapping["focus_billed_cost"]

    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if "cost" not in mapping:
        missing.append("cost")
    unmapped = [h for h in headers if h not in used]
    return SchemaMapping(list(headers), mapping, unmapped, schema, missing)
