"""DEMO DATA generator.

Writes synthetic Azure Cost Management export files (modern camelCase ActualCost /
AmortizedCost schema, v2 export layout with manifest.json) into the local export
directory. The files are then ingested by the *real* ingestion pipeline, so demo mode
exercises schema mapping, normalisation, allocation, staging, replace-by-slice,
aggregation and anomaly detection exactly as production data would.

Scenario guarantee: across all demo subscriptions, the actual cost of the previous
complete week is exactly 100,000.00 USD and of the latest complete week 110,000.00 USD,
split by service category as specified (cents allocated with the largest-remainder
method). Reports compute these numbers from the ingested records -- nothing is hardcoded
in the reporting layer.

A revised month-to-date run is also generated for the month containing the previous
week, to demonstrate that cumulative export snapshots replace (not append) data.
"""

from __future__ import annotations

import csv
import json
import math
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.analytics.allocation import DEFAULT_CATEGORY_RULES, AllocationEngine, _Rule
from app.analytics.periods import add_months, month_end, month_start, week_start
from app.demo.catalog import REFUND, RESERVATION, SCENARIO_CURRENT, SCENARIO_PREVIOUS, STREAMS, SUBSCRIPTIONS, Event, M, Stream

CONTAINER = "cost-exports"
DATASETS = ("actual", "amortized")
REGION_DISPLAY = {"eastus": "US East", "eastus2": "US East 2", "westeurope": "EU West"}
HEADERS = [
    "invoiceSectionName", "billingAccountName", "billingProfileName", "costCenter", "billingPeriodStartDate",
    "billingPeriodEndDate", "date", "serviceFamily", "productOrderName", "consumedService", "meterId", "meterName",
    "meterCategory", "meterSubCategory", "meterRegion", "ProductName", "SubscriptionId", "subscriptionName",
    "publisherType", "resourceGroupName", "ResourceId", "resourceLocation", "effectivePrice", "quantity",
    "unitOfMeasure", "chargeType", "billingCurrency", "costInBillingCurrency", "costInUsd",
    "paygCostInBillingCurrency", "unitPrice", "PayGPrice", "frequency", "pricingModel", "benefitId", "benefitName",
    "additionalInfo", "tags",
]
PROFILES = {
    "prod": ([1, 1, 1, 1, 1, 1, 1], 0.03),
    "prod_business": ([1.06, 1.06, 1.06, 1.06, 1.06, 0.85, 0.85], 0.04),
    "nonprod_247": ([1, 1, 1, 1, 1, 1, 1], 0.05),
    "nonprod_office": ([1, 1, 1, 1, 1, 0.15, 0.15], 0.06),
    "storage": ([1, 1, 1, 1, 1, 1, 1], 0.008),
}


@dataclass
class DemoWindow:
    as_of: date
    current_start: date
    previous_start: date
    history_start: date
    reservation_start: date
    refund_date: date


def demo_window(today: date | None = None, week_start_isodow: int = 1) -> DemoWindow:
    today = today or datetime.now(UTC).date()
    as_of = week_start(today, week_start_isodow) - timedelta(days=1)  # end of the latest complete week
    cur = as_of - timedelta(days=6)
    return DemoWindow(
        as_of=as_of,
        current_start=cur,
        previous_start=cur - timedelta(days=7),
        history_start=date(as_of.year - 1, 1, 1),
        reservation_start=month_start(add_months(as_of, -9)),
        refund_date=as_of - timedelta(days=48),
    )


def _token(tok: str | None, w: DemoWindow) -> date | None:
    if tok is None:
        return None
    if tok.startswith("cur"):
        base, rest = w.current_start, tok[3:]
    elif tok.startswith("prev"):
        base, rest = w.previous_start, tok[4:]
    else:
        return date.fromisoformat(tok)
    return base + timedelta(days=int(rest or 0))


def _event_mult(ev: Event, d: date, w: DemoWindow) -> float:
    s = _token(ev.start, w)
    e = _token(ev.end, w)
    if ev.kind in ("scale", "spike"):
        return ev.factor if (d >= s and (e is None or d <= e)) else 1.0
    if ev.kind == "ramp":
        if d < s:
            return 1.0
        if e is None or d >= e:
            return ev.factor
        return 1.0 + (ev.factor - 1.0) * (d - s).days / max((e - s).days, 1)
    if ev.kind == "weekly_growth":
        return 1.0 if d < s else ev.factor ** ((d - s).days // 7 + 1)
    raise ValueError(ev.kind)


def _resource_id(sub_guid: str, s: Stream) -> str:
    parts = s.rtype.split("/")
    ns, types = parts[0], parts[1:]
    names = ([s.parent] if s.parent else []) + [s.name]
    path = "/".join(f"{t}/{n}" for t, n in zip(types, names, strict=False))
    return f"/subscriptions/{sub_guid}/resourceGroups/{s.rg}/providers/{ns}/{path}"


def _allocate_cents(values: list[float], total_cents: int) -> list[int]:
    s = sum(values)
    if s <= 0:
        return [0] * len(values)
    scaled = [v * total_cents / s for v in values]
    floors = [math.floor(x) for x in scaled]
    remainder = total_cents - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (scaled[i] - floors[i]), reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _engine() -> AllocationEngine:
    rules = [_Rule(i, f, p.lower(), c, prio) for i, (prio, f, p, c) in enumerate(DEFAULT_CATEGORY_RULES)]
    return AllocationEngine(subscriptions={}, environments={}, environment_groups={}, applications={}, app_mappings=[],
                            tag_mappings=[], category_rules=rules, precedence=["subscription"])


def _fmt_date(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def generate_demo_exports(root: str | Path, today: date | None = None, week_start_isodow: int = 1) -> dict[str, Any]:
    w = demo_window(today, week_start_isodow)
    rng = random.Random(20261106)
    subs = {i: (guid, name, region) for i, _app, _env, guid, name, region in SUBSCRIPTIONS}
    engine = _engine()
    ref = w.previous_start + timedelta(days=3)
    days = [w.history_start + timedelta(days=i) for i in range((w.as_of - w.history_start).days + 1)]

    # 1) validate categories against the production classification rules
    for s in STREAMS:
        m = M[s.meter]
        rid = _resource_id(subs[s.sub][0], s)
        row = {"resource_group": s.rg.lower(), "resource_type": "/".join([s.rtype.split("/")[0]] + s.rtype.split("/")[1:]).lower(),
               "meter_category": m.category, "meter_subcategory": m.subcategory, "meter_name": m.name, "service_name": m.category,
               "consumed_service": m.consumed_service, "resource_key": rid.lower()}
        got = engine.categorize(row)
        if got != s.category:
            raise AssertionError(f"Demo stream {s.name}/{s.meter}: expected category {s.category}, rules produce {got}")

    # 2) float daily costs per stream
    costs: dict[int, dict[date, float]] = defaultdict(dict)
    for si, s in enumerate(STREAMS):
        weekly, sd = PROFILES[s.profile]
        norm = sum(weekly) / 7
        a_from, a_to = _token(s.active_from, w), _token(s.active_to, w)
        for d in days:
            if (a_from and d < a_from) or (a_to and d > a_to):
                continue
            v = s.base / norm * weekly[d.isoweekday() - 1]
            v *= (1 + s.growth) ** ((d - ref).days / 30.44)
            for ev in s.events:
                v *= _event_mult(ev, d, w)
            v *= max(0.5, rng.gauss(1.0, sd))
            costs[si][d] = v

    # reserved VM usage: actual cost 0 once the reservation applies
    def reserved(si: int, d: date) -> bool:
        s = STREAMS[si]
        return s.reserved_from is not None and d >= w.reservation_start

    # 3) cents: exact scenario totals for the two scenario weeks, rounded elsewhere
    cents: dict[int, dict[date, int]] = defaultdict(dict)
    scenario_weeks = [(w.previous_start, SCENARIO_PREVIOUS), (w.current_start, SCENARIO_CURRENT)]
    in_scenario: set[date] = set()
    for start, targets in scenario_weeks:
        week_days = [start + timedelta(days=i) for i in range(7)]
        in_scenario |= set(week_days)
        for cat, target in targets.items():
            keys = [(si, d) for si, s in enumerate(STREAMS) if s.category == cat for d in week_days if d in costs[si] and not reserved(si, d)]
            alloc = _allocate_cents([costs[si][d] for si, d in keys], int(target * 100))
            for (si, d), c in zip(keys, alloc, strict=False):
                cents[si][d] = c
    for si in costs:
        for d, v in costs[si].items():
            if d in in_scenario:
                cents[si].setdefault(d, 0)
                continue
            cents[si][d] = 0 if reserved(si, d) else int(round(v * 100))

    # 4) rows per (subscription, dataset, month)
    rows: dict[tuple[int, str, date], list[dict[str, str]]] = defaultdict(list)
    for si, s in enumerate(STREAMS):
        guid, sub_name, region = subs[s.sub]
        m = M[s.meter]
        rid = _resource_id(guid, s)
        tags = json.dumps(s.tags) if s.tags else ""
        addl = json.dumps({"ServiceType": m.service_type, "UsageType": "ComputeHR"}) if m.service_type else ""
        for d, c in sorted(cents[si].items()):
            cost = Decimal(c) / 100
            is_res = reserved(si, d)
            for ds in DATASETS:
                if is_res:
                    qty_v = Decimal(24)
                    row_cost = Decimal(str(s.reserved_daily_amortized)).quantize(Decimal("0.01")) if ds == "amortized" else Decimal(0)
                    eff = (row_cost / qty_v).quantize(Decimal("0.000001"))
                    pricing, benefit_id, benefit_name = "Reservation", RESERVATION["id"], RESERVATION["name"]
                else:
                    qty_v = (cost / m.price).quantize(Decimal("0.000001")) if m.price else Decimal(0)
                    row_cost, eff = cost, m.price
                    pricing, benefit_id, benefit_name = "OnDemand", "", ""
                rows[(s.sub, ds, month_start(d))].append({
                    "invoiceSectionName": "DEMO Invoice Section",
                    "billingAccountName": "DEMO Billing Account (synthetic)",
                    "billingProfileName": "DEMO Billing Profile",
                    "costCenter": "",
                    "billingPeriodStartDate": _fmt_date(month_start(d)),
                    "billingPeriodEndDate": _fmt_date(month_end(d)),
                    "date": _fmt_date(d),
                    "serviceFamily": m.service_family,
                    "productOrderName": "",
                    "consumedService": m.consumed_service,
                    "meterId": m.meter_id,
                    "meterName": m.name,
                    "meterCategory": m.category,
                    "meterSubCategory": m.subcategory,
                    "meterRegion": REGION_DISPLAY.get(region, region),
                    "ProductName": m.product,
                    "SubscriptionId": guid,
                    "subscriptionName": sub_name,
                    "publisherType": "Microsoft",
                    "resourceGroupName": s.rg,
                    "ResourceId": rid,
                    "resourceLocation": region,
                    "effectivePrice": f"{eff}",
                    "quantity": f"{qty_v}",
                    "unitOfMeasure": m.unit,
                    "chargeType": "Usage",
                    "billingCurrency": "USD",
                    "costInBillingCurrency": f"{row_cost:.2f}",
                    "costInUsd": f"{row_cost:.2f}",
                    "paygCostInBillingCurrency": f"{(qty_v * m.price):.2f}",
                    "unitPrice": f"{m.price}",
                    "PayGPrice": f"{m.price}",
                    "frequency": "UsageBased",
                    "pricingModel": pricing,
                    "benefitId": benefit_id,
                    "benefitName": benefit_name,
                    "additionalInfo": addl,
                    "tags": tags,
                })

    # reservation purchase (actual cost only; amortized spreads it over usage rows)
    rs = RESERVATION
    g1, n1, r1 = subs[rs["subscription"]]
    rows[(rs["subscription"], "actual", month_start(w.reservation_start))].append({
        **{h: "" for h in HEADERS},
        "invoiceSectionName": "DEMO Invoice Section", "billingAccountName": "DEMO Billing Account (synthetic)", "billingProfileName": "DEMO Billing Profile",
        "billingPeriodStartDate": _fmt_date(month_start(w.reservation_start)), "billingPeriodEndDate": _fmt_date(month_end(w.reservation_start)),
        "date": _fmt_date(w.reservation_start), "serviceFamily": "Compute", "consumedService": "Microsoft.Capacity",
        "meterCategory": "Virtual Machines", "meterSubCategory": "Reservation-Base VM", "meterName": "Reserved VM Instance",
        "ProductName": "Reserved VM Instance, Standard_E8s_v5, US East, 1 Year", "SubscriptionId": g1, "subscriptionName": n1,
        "publisherType": "Microsoft", "quantity": "4", "unitOfMeasure": "1", "chargeType": "Purchase", "billingCurrency": "USD",
        "costInBillingCurrency": f"{rs['amount']:.2f}", "costInUsd": f"{rs['amount']:.2f}", "frequency": "OneTime",
        "pricingModel": "Reservation", "benefitId": rs["id"], "benefitName": rs["name"], "resourceLocation": r1,
    })
    # SLA credit refund (negative charge) on an App Service plan
    gr, nr, rr = subs[REFUND["subscription"]]
    sref = next(s for s in STREAMS if s.name == REFUND["resource"])
    for ds in DATASETS:
        rows[(REFUND["subscription"], ds, month_start(w.refund_date))].append({
            **{h: "" for h in HEADERS},
            "invoiceSectionName": "DEMO Invoice Section", "billingAccountName": "DEMO Billing Account (synthetic)", "billingProfileName": "DEMO Billing Profile",
            "billingPeriodStartDate": _fmt_date(month_start(w.refund_date)), "billingPeriodEndDate": _fmt_date(month_end(w.refund_date)),
            "date": _fmt_date(w.refund_date), "serviceFamily": "Compute", "consumedService": "Microsoft.Web",
            "meterId": M["asp"].meter_id, "meterCategory": "Azure App Service", "meterSubCategory": "Premium v3 Plan", "meterName": "P2 v3",
            "ProductName": "SLA credit (DEMO)", "SubscriptionId": gr, "subscriptionName": nr, "publisherType": "Microsoft",
            "resourceGroupName": sref.rg, "ResourceId": _resource_id(gr, sref), "resourceLocation": rr, "quantity": "0",
            "unitOfMeasure": "1 Hour", "chargeType": "Refund", "billingCurrency": "USD",
            "costInBillingCurrency": f"{REFUND['amount']:.2f}", "costInUsd": f"{REFUND['amount']:.2f}", "frequency": "OneTime",
            "pricingModel": "OnDemand", "tags": json.dumps(sref.tags),
        })

    # 5) write runs
    root = Path(root)
    files_written = 0
    rows_written = 0
    revision_month = month_start(w.previous_start)
    definitions: list[dict[str, Any]] = []
    for idx, _app, _env, guid, _name, _region in SUBSCRIPTIONS:
        for ds in DATASETS:
            folder = f"demo/{guid}/{ds}"
            export_name = f"acip-{ds}-daily"
            definitions.append({"subscription_guid": guid, "dataset_type": ds, "root_folder_path": folder, "export_name": export_name})
            months = sorted({k[2] for k in rows if k[0] == idx and k[1] == ds})
            for ms in months:
                data = rows[(idx, ds, ms)]
                me = month_end(ms)
                complete = me <= w.as_of
                submitted = datetime.combine((me if complete else w.as_of) + timedelta(days=1 if not complete else 2), time(6, 0), tzinfo=UTC)
                variants = [("final", data, submitted)]
                if ds == "actual" and ms == revision_month:
                    cutoff = min(me, w.as_of - timedelta(days=5))
                    early = []
                    for r in data:
                        d = datetime.strptime(r["date"], "%m/%d/%Y").date()
                        if d <= cutoff:
                            r2 = dict(r)
                            if r["chargeType"] == "Usage":
                                c = (Decimal(r["costInBillingCurrency"]) * Decimal("0.985")).quantize(Decimal("0.01"))
                                r2["costInBillingCurrency"] = f"{c:.2f}"
                                r2["costInUsd"] = f"{c:.2f}"
                            early.append(r2)
                    variants.insert(0, ("early", early, datetime.combine(cutoff + timedelta(days=1), time(6, 0), tzinfo=UTC)))
                for variant, vrows, sub_at in variants:
                    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"acip-demo/{guid}/{ds}/{ms.isoformat()}/{variant}"))
                    period = f"{ms:%Y%m%d}-{me:%Y%m%d}"
                    rel = f"{folder}/{export_name}/{period}/{run_id}"
                    target = root / CONTAINER / rel
                    target.mkdir(parents=True, exist_ok=True)
                    part = target / "part_0_0001.csv"
                    with open(part, "w", newline="", encoding="utf-8") as fh:
                        wr = csv.DictWriter(fh, fieldnames=HEADERS)
                        wr.writeheader()
                        wr.writerows(vrows)
                    manifest = {
                        "manifestVersion": "2024-04-01",
                        "byteCount": part.stat().st_size,
                        "blobCount": 1,
                        "dataRowCount": len(vrows),
                        "exportConfig": {
                            "exportName": export_name,
                            "resourceId": f"/subscriptions/{guid}/providers/Microsoft.CostManagement/exports/{export_name}",
                            "dataVersion": "2023-12-01-preview",
                            "apiVersion": "2023-07-01-preview",
                            "type": "ActualCost" if ds == "actual" else "AmortizedCost",
                            "timeFrame": "MonthToDate" if not complete else "TheLastMonth",
                            "granularity": "Daily",
                            "demo": True,
                        },
                        "deliveryConfig": {"partitionData": True, "dataOverwriteBehavior": "CreateNewReport", "fileFormat": "Csv",
                                           "compressionMode": "None", "containerUri": f"local://{CONTAINER}", "rootFolderPath": folder},
                        "runInfo": {"executionType": "Scheduled", "submittedTime": sub_at.isoformat().replace("+00:00", "Z"), "runId": run_id,
                                    "startDate": f"{ms.isoformat()}T00:00:00", "endDate": f"{me.isoformat()}T00:00:00"},
                        "blobs": [{"blobName": f"{rel}/part_0_0001.csv", "byteCount": part.stat().st_size, "dataRowCount": len(vrows)}],
                    }
                    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
                    files_written += 1
                    rows_written += len(vrows)

    scenario_check = {}
    for label, start in (("previous_week", w.previous_start), ("current_week", w.current_start)):
        tot = sum(cents[si][start + timedelta(days=i)] for si in cents for i in range(7) if (start + timedelta(days=i)) in cents[si])
        scenario_check[label] = str(Decimal(tot) / 100)
    return {
        "as_of": w.as_of.isoformat(),
        "current_week": [w.current_start.isoformat(), w.as_of.isoformat()],
        "previous_week": [w.previous_start.isoformat(), (w.current_start - timedelta(days=1)).isoformat()],
        "history_start": w.history_start.isoformat(),
        "files_written": files_written,
        "rows_written": rows_written,
        "scenario_totals": scenario_check,
        "definitions": definitions,
        "container": CONTAINER,
    }
