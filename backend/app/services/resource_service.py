"""Resource analysis, meter-level root cause and billing-record drill-down."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.analytics import periods as P
from app.analytics.comparison import money, price, qty, sort_items
from app.analytics.decomposition import MeterRow, decompose
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import AzureResource, CostAnomaly, CostRecord, SavingsOpportunity
from app.repositories.cost_repository import CostRepository
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService, item_out

METER_DIMS = ["resource", "meter_category", "meter_subcategory", "meter_name", "unit", "charge_type", "pricing_model", "sku"]


def _resource_or_404(db: Session, resource_id: int) -> AzureResource:
    r = db.get(AzureResource, resource_id)
    if r is None:
        raise NotFoundError(f"Resource {resource_id} not found")
    return r


def list_resources(db: Session, params: ReportParams, allowed: set[int] | None, sort_dir: str = "desc") -> dict[str, Any]:
    svc = ReportingService(db, params.copy(group_by="resource"), allowed)
    scope = svc.scope()
    items, (tp, tc, _) = svc.compared_groups(scope, "resource", resource_attributes=True)
    has_cmp = scope.comparison is not None
    ranked = sort_items(items, params.sort if has_cmp or params.sort in ("current_cost", "name", "previous_cost") else "current_cost")
    # sort_items returns "name" ascending and every other key descending
    if (sort_dir == "asc") != (params.sort == "name"):
        ranked.reverse()
    start = (params.page - 1) * params.page_size
    page = ranked[start : start + params.page_size]
    keys = [i.key for i in page if i.key]

    inventory = {}
    if keys:
        for r in db.execute(select(AzureResource).where(AzureResource.resource_key.in_(keys))).scalars():
            inventory[r.resource_key] = r
    primary: dict[str, dict[str, Any]] = {}
    if keys:
        repo = svc.repo
        f = scope.filters
        rows = repo.grouped_compare(
            type(f)(**{**f.__dict__, "resource_keys": keys}), scope.current.period, None,
            ["resource", "meter_category", "meter_name", "unit"], with_quantity=True,
        )
        for r in rows:  # ordered by current cost desc -> first row per resource is the primary meter
            k = r.values["resource_key"]
            if k not in primary:
                primary[k] = {
                    "meter_category": r.values["meter_category"],
                    "meter_name": r.values["meter_name"],
                    "unit": r.values["unit_of_measure"],
                    "quantity": qty(r.current_qty),
                    "meter_count": 0,
                }
            primary[k]["meter_count"] += 1

    data = []
    for i in page:
        row = item_out(i, has_cmp)
        inv = inventory.get(i.key)
        a = i.attributes
        row.update(
            id=inv.id if inv else None,
            resource_id=inv.resource_id if inv else i.key,
            resource_name=i.label,
            subscription_id=a.get("subscription_id"),
            subscription_name=a.get("subscription_name"),
            application=a.get("application_name"),
            application_key=a.get("application_key"),
            environment=a.get("environment_name"),
            environment_code=a.get("environment_code"),
            resource_group=a.get("resource_group"),
            resource_type=a.get("resource_type"),
            service_category=a.get("service_category"),
            region=a.get("region"),
            owner=a.get("owner"),
            cost_center=a.get("cost_center"),
            sku=inv.sku if inv else None,
            tags=inv.tags if inv else None,
            first_seen_date=inv.first_seen_date.isoformat() if inv and inv.first_seen_date else None,
            billing_currency=scope.currency,
            primary_meter=primary.get(i.key),
        )
        row.pop("attributes", None)
        data.append(row)
    return {
        "data": data,
        "meta": svc.meta(scope, page=params.page, page_size=params.page_size, total=len(ranked), totals=svc.totals_out(scope, tp, tc), sort=params.sort, sort_dir=sort_dir),
    }


def resource_detail(db: Session, resource_id: int, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    r = _resource_or_404(db, resource_id)
    if allowed is not None and r.subscription_fk not in allowed:
        raise NotFoundError(f"Resource {resource_id} not found")
    svc = ReportingService(db, params.copy(resource=[r.resource_key], group_by="meter"), allowed)
    scope = svc.scope()
    items, (tp, tc, _) = svc.compared_groups(scope, "meter")
    labels = svc.labels
    app_key, app_name = labels.application(r.application_id, r.allocation_status)
    env_code, env_name = labels.environment(r.environment_id)
    sub_guid, sub_name = labels.subscription(r.subscription_fk)
    anomalies = db.execute(select(func.count()).select_from(CostAnomaly).where(CostAnomaly.resource_key == r.resource_key)).scalar_one()
    open_anoms = db.execute(
        select(func.count()).select_from(CostAnomaly).where(CostAnomaly.resource_key == r.resource_key, CostAnomaly.status.in_(["open", "investigating"]))
    ).scalar_one()
    savings = [
        {"id": s.id, "title": s.title, "estimated_monthly_savings": money(s.estimated_monthly_savings), "status": s.status, "evidence_source": s.evidence_source}
        for s in db.execute(select(SavingsOpportunity).where(SavingsOpportunity.resource_key == r.resource_key)).scalars()
    ]
    return {
        "data": {
            "resource": {
                "id": r.id,
                "resource_id": r.resource_id,
                "resource_key": r.resource_key,
                "resource_name": r.resource_name,
                "resource_type": r.resource_type,
                "resource_group": r.resource_group,
                "region": r.region,
                "sku": r.sku,
                "service_category": r.service_category,
                "subscription_id": sub_guid,
                "subscription_name": sub_name,
                "application_key": app_key,
                "application": app_name,
                "environment_code": env_code,
                "environment": env_name,
                "allocation_status": r.allocation_status,
                "owner": r.owner,
                "cost_center": r.cost_center,
                "tags": r.tags or {},
                "first_seen_date": r.first_seen_date.isoformat() if r.first_seen_date else None,
                "last_seen_date": r.last_seen_date.isoformat() if r.last_seen_date else None,
                "is_demo": r.is_demo,
            },
            "totals": svc.totals_out(scope, tp, tc),
            "meters": [item_out(i, scope.comparison is not None) for i in sort_items(items, "current_cost")],
            "anomaly_count": anomalies,
            "open_anomaly_count": open_anoms,
            "savings": savings,
        },
        "meta": svc.meta(scope),
    }


def resource_history(db: Session, resource_id: int, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    r = _resource_or_404(db, resource_id)
    if allowed is not None and r.subscription_fk not in allowed:
        raise NotFoundError(f"Resource {resource_id} not found")
    svc = ReportingService(db, params.copy(resource=[r.resource_key]), allowed)
    scope = svc.scope()
    repo: CostRepository = svc.repo
    f = scope.filters
    a = scope.as_of
    daily_p = P.Period(a - timedelta(days=89), a)
    monthly_p = P.Period(P.add_months(P.month_start(a), -12), a)
    daily = {row["bucket"]: Decimal(row["cost"]) for row in repo.series(f, daily_p, "daily")}
    monthly = {row["bucket"]: Decimal(row["cost"]) for row in repo.series(f, monthly_p, "monthly")}
    meter_rows = repo.series(f, daily_p, "daily", ["meter_name", "unit"], with_quantity=True)
    meters: dict[str, dict[str, Any]] = {}
    days = P.buckets(daily_p, "daily")
    idx = {d: i for i, d in enumerate(days)}
    for row in meter_rows:
        k = f"{row['meter_name']}|{row['unit_of_measure']}"
        m = meters.setdefault(k, {"meter_name": row["meter_name"], "unit": row["unit_of_measure"], "cost": [0.0] * len(days), "quantity": [0.0] * len(days), "total": Decimal(0)})
        i = idx[row["bucket"]]
        m["cost"][i] = money(Decimal(row["cost"]))
        m["quantity"][i] = qty(Decimal(row["quantity"] or 0))
        m["total"] += Decimal(row["cost"])
    top = sorted(meters.values(), key=lambda m: -m["total"])[:6]
    for m in top:
        m["total"] = money(m["total"])
    return {
        "data": {
            "daily": [{"date": d.isoformat(), "cost": money(daily.get(d, Decimal(0)))} for d in days],
            "monthly": [{"month": b.isoformat(), "cost": money(monthly.get(b, Decimal(0)))} for b in P.buckets(monthly_p, "monthly")],
            "meters": top,
            "dates": [d.isoformat() for d in days],
        },
        "meta": svc.meta(scope),
    }


def meter_comparison(db: Session, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    """Meter-level 'what changed' decomposition for any filter scope."""
    svc = ReportingService(db, params, allowed)
    scope = svc.scope()
    if scope.comparison is None:
        from app.core.errors import ValidationFailed

        raise ValidationFailed("Meter-level comparison requires a comparison period")
    rows = svc.repo.grouped_compare(scope.filters, scope.current.period, scope.comparison, METER_DIMS, with_quantity=True)
    meter_rows = []
    for r in rows:
        v = r.values
        meter_key = "|".join(str(v.get(c) or "") for c in ("meter_category", "meter_subcategory", "meter_name", "unit_of_measure"))
        meter_rows.append(
            MeterRow(
                resource_key=v["resource_key"] or "",
                resource_name=r.label_hint,
                meter_key=meter_key,
                meter_category=v.get("meter_category"),
                meter_subcategory=v.get("meter_subcategory"),
                meter_name=v.get("meter_name"),
                unit=v.get("unit_of_measure"),
                charge_type=v.get("charge_type"),
                pricing_model=v.get("pricing_model"),
                sku=v.get("sku"),
                prev_cost=r.previous,
                cur_cost=r.current,
                prev_qty=r.previous_qty or Decimal(0),
                cur_qty=r.current_qty or Decimal(0),
                prev_records=r.previous_records,
                cur_records=r.current_records,
            )
        )
    result = decompose(meter_rows)
    result["meters"] = result["meters"][:300]
    result["resources"] = result["resources"][:300]
    return {"data": result, "meta": svc.meta(scope, evidence_note=(
        "Confirmed facts are calculated directly from billing records. Hypotheses are possible explanations that billing data "
        "cannot prove; verify them with Azure Activity Log, Resource Graph or Azure Monitor before acting."
    ))}


def resource_meters(db: Session, resource_id: int, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    r = _resource_or_404(db, resource_id)
    if allowed is not None and r.subscription_fk not in allowed:
        raise NotFoundError(f"Resource {resource_id} not found")
    return meter_comparison(db, params.copy(resource=[r.resource_key]), allowed)


RECORD_COLUMNS = [
    "usage_date", "billing_currency", "cost", "quantity", "unit_of_measure", "effective_price", "unit_price",
    "meter_category", "meter_subcategory", "meter_name", "sku", "charge_type", "pricing_model", "frequency",
    "resource_name", "resource_group", "resource_type", "region", "service_category", "service_name",
    "benefit_name", "tags", "export_run_id", "ingestion_file_id", "source_row_number", "normalizer_version",
]


def billing_records(db: Session, params: ReportParams, allowed: set[int] | None, include_comparison: bool = False) -> dict[str, Any]:
    """Exact billing records behind a view (raw cost_records, server-side paginated)."""
    svc = ReportingService(db, params, allowed)
    scope = svc.scope()
    t = CostRecord.__table__
    from app.repositories.cost_repository import TABLES

    raw_spec = TABLES[-1]
    where = svc.repo._where(t, scope.filters, raw_spec)
    date_cond = t.c.usage_date.between(scope.current.period.start, scope.current.period.end)
    if include_comparison and scope.comparison:
        date_cond = or_(date_cond, t.c.usage_date.between(scope.comparison.start, scope.comparison.end))
    base = and_(*where, date_cond)
    total = db.execute(select(func.count()).select_from(t).where(base)).scalar_one()
    p = params
    cols = [t.c[c] for c in RECORD_COLUMNS] + [t.c.subscription_fk, t.c.resource_key, t.c.id]
    stmt = select(*cols).where(base).order_by(t.c.usage_date.desc(), t.c.cost.desc(), t.c.id).offset((p.page - 1) * p.page_size).limit(p.page_size)
    rows = []
    for r in db.execute(stmt).mappings():
        d = dict(r)
        d["usage_date"] = d["usage_date"].isoformat()
        d["cost"] = money(d["cost"], 6)
        d["quantity"] = qty(d["quantity"]) if d["quantity"] is not None else None
        d["effective_price"] = price(d["effective_price"]) if d["effective_price"] is not None else None
        d["unit_price"] = price(d["unit_price"]) if d["unit_price"] is not None else None
        d["subscription_id"], d["subscription_name"] = svc.labels.subscription(d.pop("subscription_fk"))
        d["period"] = "current" if scope.current.period.contains(r["usage_date"]) else "comparison"
        rows.append(d)
    return {"data": rows, "meta": svc.meta(scope, page=p.page, page_size=p.page_size, total=total)}


def resource_anomalies(db: Session, resource_id: int, allowed: set[int] | None) -> list[CostAnomaly]:
    r = _resource_or_404(db, resource_id)
    if allowed is not None and r.subscription_fk not in allowed:
        raise NotFoundError(f"Resource {resource_id} not found")
    return list(db.execute(select(CostAnomaly).where(CostAnomaly.resource_key == r.resource_key).order_by(CostAnomaly.detection_date.desc())).scalars())


def resource_activity(db: Session, resource_id: int, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    """Optional supporting evidence from Azure Activity Log (configuration changes)."""
    r = _resource_or_404(db, resource_id)
    settings = get_settings()
    if not settings.azure_enabled or r.is_demo:
        return {
            "available": False,
            "reason": "Azure Activity Log integration is not available for demo data or when Azure integration is disabled.",
            "events": [],
        }
    from app.integrations.azure_cost_management.client import ArmClient, ArmError

    svc = ReportingService(db, params.copy(resource=[r.resource_key]), allowed)
    scope = svc.scope()
    start = scope.comparison.start if scope.comparison else scope.current.period.start
    sub_guid, _ = svc.labels.subscription(r.subscription_fk)
    try:
        events = ArmClient().list_activity_log(sub_guid, r.resource_id, start, scope.current.period.end)
    except ArmError as exc:
        return {"available": False, "reason": f"Activity Log query failed: {exc.code} {exc.message}", "events": []}
    out = []
    for e in events[:200]:
        out.append({
            "timestamp": e.get("eventTimestamp"),
            "operation": (e.get("operationName") or {}).get("localizedValue"),
            "status": (e.get("status") or {}).get("localizedValue"),
            "caller": e.get("caller"),
            "level": e.get("level"),
        })
    return {"available": True, "reason": None, "events": out, "note": "Activity Log entries are supporting evidence of configuration changes; correlate with billing changes before drawing conclusions."}
