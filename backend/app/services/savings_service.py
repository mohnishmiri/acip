"""Evidence-based potential savings.

Billing data shows *what was billed* (hours, GB, operations) -- not CPU or memory
utilisation. Rules here therefore only make claims billing data supports (for example
"billed 24 hours a day including weekends"), state their assumptions, and leave the
savings estimate empty when it cannot be estimated responsibly. Utilisation-based
recommendations come from Azure Advisor (optional integration).

Estimated savings are never labelled as realised savings, and nothing here modifies
Azure resources.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.comparison import ZERO, money, pct_change
from app.analytics.periods import Period
from app.models import AzureResource, AzureSubscription, CostAnomaly, DailyCostAggregate, SavingsOpportunity
from app.repositories.cost_repository import CostFilters, CostRepository
from app.services import settings_service
from app.services.labels import LabelResolver

log = logging.getLogger(__name__)

STATUSES = ("open", "investigating", "accepted", "dismissed", "implemented")


def _upsert(db: Session, key: str, values: dict[str, Any], created: list[int]) -> SavingsOpportunity:
    o = db.execute(select(SavingsOpportunity).where(SavingsOpportunity.opportunity_key == key)).scalar_one_or_none()
    if o is None:
        o = SavingsOpportunity(opportunity_key=key, status="open", **values)
        db.add(o)
        db.flush()
        created.append(o.id)
    else:
        for k, v in values.items():
            setattr(o, k, v)
        o.last_evaluated_at = datetime.now(UTC)
    return o


def evaluate_savings(db: Session, dataset_type: str = "actual") -> dict[str, Any]:
    ws = settings_service.week_start(db)
    repo = CostRepository(db, ws)
    labels = LabelResolver(db)
    min_monthly = Decimal(str(settings_service.get_setting(db, "savings.min_monthly_cost")))
    schedule_hours = Decimal(str(settings_service.get_setting(db, "savings.nonprod_schedule_hours_per_week")))
    t = DailyCostAggregate.__table__
    currencies = [r[0] for r in db.execute(select(t.c.billing_currency).where(t.c.dataset_type == dataset_type).distinct())]
    created: list[int] = []
    evaluated = 0
    nonprod_env_ids = [e.id for e in labels.envs.values() if e.environment_group == "non_production"]
    inventory = {r.resource_key: r for r in db.execute(select(AzureResource)).scalars()}

    for cur in currencies:
        f = CostFilters(dataset_type=dataset_type, currency=cur, charge_types=["Usage"])
        _, data_end = repo.date_bounds(f)
        as_of = settings_service.complete_through(db, data_end)
        if as_of is None:
            continue
        p14 = Period(as_of - timedelta(days=13), as_of)
        p30 = Period(as_of - timedelta(days=29), as_of)
        prev30 = Period(as_of - timedelta(days=59), as_of - timedelta(days=30))

        # Rule 1: Non-Production compute billed around the clock, including weekends.
        nf = CostFilters(**{**f.__dict__, "environment_ids": nonprod_env_ids or [-1], "service_categories": ["Virtual Machines", "Azure Kubernetes Service"]})
        rows = repo.series(nf, p14, "daily", ["resource", "unit"], with_quantity=True)
        per: dict[str, dict[str, Any]] = defaultdict(lambda: {"wd": [], "we": [], "cost": ZERO})
        for r in rows:
            if not r["resource_key"] or "hour" not in (r["unit_of_measure"] or "").lower():
                continue
            q = Decimal(r["quantity"] or 0)
            (per[r["resource_key"]]["we"] if r["bucket"].isoweekday() >= 6 else per[r["resource_key"]]["wd"]).append(q)
        cost30 = {g.values["resource_key"]: g.current for g in repo.grouped_compare(nf, p30, None, ["resource"])}
        for rk, v in per.items():
            evaluated += 1
            if len(v["wd"]) < 8 or len(v["we"]) < 2:
                continue
            wd = sum(v["wd"], ZERO) / Decimal(len(v["wd"]))
            we = sum(v["we"], ZERO) / Decimal(len(v["we"]))
            monthly = cost30.get(rk, ZERO)
            if wd <= 0 or monthly < min_monthly or we / wd < Decimal("0.9"):
                continue
            res = inventory.get(rk)
            est = monthly * (Decimal(1) - schedule_hours / Decimal(168))
            _upsert(db, f"NONPROD_ALWAYS_ON:{rk}", {
                "rule_code": "NONPROD_ALWAYS_ON",
                "title": f"Non-Production compute billed 24×7: {res.resource_name if res else rk.rsplit('/', 1)[-1]}",
                "resource_key": rk,
                "resource_name": res.resource_name if res else None,
                "subscription_fk": res.subscription_fk if res else None,
                "application_id": res.application_id if res else None,
                "environment_id": res.environment_id if res else None,
                "service_category": res.service_category if res else None,
                "billing_currency": cur,
                "current_monthly_cost": monthly,
                "estimated_monthly_savings": est.quantize(Decimal("0.01")),
                "savings_basis": f"Assumes an operating schedule of {schedule_hours} hours/week instead of 168 (configurable). Actual savings depend on workload requirements.",
                "issue": "Billing shows the same compute hours on weekends as on weekdays in a Non-Production environment, i.e. the resource is billed around the clock.",
                "evidence": {
                    "evaluation_period": [p14.start.isoformat(), p14.end.isoformat()],
                    "avg_weekday_billed_hours": float(round(wd, 2)),
                    "avg_weekend_billed_hours": float(round(we, 2)),
                    "weekend_to_weekday_ratio": float(round(we / wd, 3)),
                    "cost_last_30_days": money(monthly),
                    "note": "Billed hours are not CPU utilisation; the workload may legitimately need to run continuously.",
                },
                "recommendation": "Confirm with the owner whether the environment must run outside business hours; if not, schedule shutdown (VM auto-shutdown, AKS cluster stop / node pool scale-to-zero).",
                "evidence_source": "billing_analysis",
                "is_demo": bool(res and res.is_demo),
            }, created)

        # Rule 2: Monitoring share of an application environment.
        app_rows = repo.grouped_compare(f, p30, None, ["application", "environment", "service_category"])
        totals: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        monitor: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        for g in app_rows:
            k = (g.values["application_id"], g.values["allocation_status"], g.values["environment_id"])
            totals[k] += g.current
            if g.values["service_category"] == "Azure Monitor":
                monitor[k] += g.current
        for k, mon in monitor.items():
            evaluated += 1
            share = mon / totals[k] * 100 if totals[k] else ZERO
            if mon < min_monthly or share < 7:
                continue
            _, app = labels.application(k[0], k[1])
            _, env = labels.environment(k[2])
            sub = next((s for s in labels.subs.values() if s.application_id == k[0] and s.environment_id == k[2]), None)
            _upsert(db, f"HIGH_MONITORING_SHARE:{k}", {
                "rule_code": "HIGH_MONITORING_SHARE",
                "title": f"High monitoring / logging cost share: {app} · {env}",
                "resource_key": None, "resource_name": None,
                "subscription_fk": sub.id if sub else None, "application_id": k[0], "environment_id": k[2],
                "service_category": "Azure Monitor", "billing_currency": cur,
                "current_monthly_cost": mon, "estimated_monthly_savings": None,
                "savings_basis": "Not estimated: the achievable reduction depends on which logs are required for operations and compliance.",
                "issue": f"Azure Monitor (Log Analytics / Application Insights) accounts for {share:.1f}% of this environment's cost over the last 30 days.",
                "evidence": {"period": [p30.start.isoformat(), p30.end.isoformat()], "monitoring_cost": money(mon), "environment_cost": money(totals[k]), "share_pct": float(round(share, 2))},
                "recommendation": "Review ingestion by table and source, diagnostic settings, verbose application logging, retention, and Basic/Auxiliary log plans for high-volume tables.",
                "evidence_source": "billing_analysis",
                "is_demo": bool(sub and sub.is_demo),
            }, created)

        # Rule 3: Network egress growth (data transfer out) per subscription.
        egress_f = CostFilters(**{**f.__dict__, "meter_categories": ["Bandwidth"]})
        for g in repo.grouped_compare(egress_f, p30, prev30, ["subscription"]):
            evaluated += 1
            inc = g.current - g.previous
            pct = pct_change(g.previous, g.current)
            if inc < 200 or pct is None or pct < 15:
                continue
            sub = labels.subs.get(g.values["subscription_fk"])
            _upsert(db, f"EGRESS_GROWTH:{g.values['subscription_fk']}", {
                "rule_code": "EGRESS_GROWTH",
                "title": f"Unexpected network egress growth: {sub.subscription_name if sub else g.values['subscription_fk']}",
                "resource_key": None, "resource_name": None,
                "subscription_fk": g.values["subscription_fk"], "application_id": sub.application_id if sub else None,
                "environment_id": sub.environment_id if sub else None, "service_category": "Networking", "billing_currency": cur,
                "current_monthly_cost": g.current, "estimated_monthly_savings": None,
                "savings_basis": "Not estimated: depends on whether the additional traffic is required.",
                "issue": f"Outbound data transfer cost rose {pct:.1f}% ({cur} {inc:,.2f}) over the last 30 days compared with the previous 30 days.",
                "evidence": {"current_30_days": money(g.current), "previous_30_days": money(g.previous), "increase": money(inc), "pct": float(round(pct, 2))},
                "recommendation": "Identify the sources of outbound traffic (flow logs / Traffic Analytics); consider caching/CDN, compression, private endpoints or same-region placement.",
                "evidence_source": "billing_analysis",
                "is_demo": bool(sub and sub.is_demo),
            }, created)

    # Rule 4: Steadily increasing resources (from continuous-increase anomalies)
    for a in db.execute(select(CostAnomaly).where(CostAnomaly.rule_code == "CONTINUOUS_INCREASE", CostAnomaly.status.in_(["open", "investigating", "acknowledged"]))).scalars():
        evaluated += 1
        _upsert(db, f"STEADY_GROWTH:{a.resource_key}", {
            "rule_code": "STEADY_GROWTH",
            "title": f"Steadily increasing cost: {a.resource_name or a.resource_key}",
            "resource_key": a.resource_key, "resource_name": a.resource_name,
            "subscription_fk": a.subscription_fk, "application_id": a.application_id, "environment_id": a.environment_id,
            "service_category": a.service_category, "billing_currency": a.billing_currency,
            "current_monthly_cost": (a.current_cost / 7 * 30).quantize(Decimal("0.01")), "estimated_monthly_savings": None,
            "savings_basis": "Not estimated: growth may be expected (e.g. data growth); review retention and tiering.",
            "issue": f"Weekly cost increased for several consecutive weeks (anomaly ANM-{a.id:06d}).",
            "evidence": {"anomaly_id": a.id, "weekly_totals": a.evidence.get("extra", {}).get("weekly_totals")},
            "recommendation": "Review data retention and lifecycle policies, storage tiering, and whether the growth matches business expectations.",
            "evidence_source": "billing_analysis",
            "is_demo": a.is_demo,
        }, created)
    return {"created_ids": created, "created": len(created), "evaluated": evaluated}


def import_advisor(db: Session) -> dict[str, Any]:
    """Import Azure Advisor cost recommendations for enabled, non-demo subscriptions."""
    from app.core.config import get_settings
    from app.integrations.azure_cost_management.client import ArmClient, ArmError

    if not get_settings().azure_enabled:
        return {"imported": 0, "reason": "Azure integration disabled"}
    client = ArmClient()
    created: list[int] = []
    errors = []
    inventory = {r.resource_key: r for r in db.execute(select(AzureResource)).scalars()}
    for sub in db.execute(select(AzureSubscription).where(AzureSubscription.enabled.is_(True), AzureSubscription.is_demo.is_(False))).scalars():
        try:
            recs = client.list_advisor_cost_recommendations(sub.subscription_id)
        except ArmError as exc:
            errors.append(f"{sub.subscription_name}: {exc.code}")
            continue
        for rec in recs:
            p = rec.get("properties", {})
            ext = p.get("extendedProperties", {}) or {}
            rk = (p.get("resourceMetadata", {}) or {}).get("resourceId", "").lower() or None
            res = inventory.get(rk) if rk else None
            monthly = ext.get("savingsAmount") or (float(ext["annualSavingsAmount"]) / 12 if ext.get("annualSavingsAmount") else None)
            _upsert(db, f"ADVISOR:{rec.get('name')}", {
                "rule_code": "AZURE_ADVISOR",
                "title": (p.get("shortDescription", {}) or {}).get("problem") or "Azure Advisor cost recommendation",
                "resource_key": rk, "resource_name": res.resource_name if res else (rk.rsplit("/", 1)[-1] if rk else None),
                "subscription_fk": sub.id, "application_id": res.application_id if res else sub.application_id,
                "environment_id": res.environment_id if res else sub.environment_id, "service_category": res.service_category if res else None,
                "billing_currency": ext.get("savingsCurrency") or sub.billing_currency,
                "current_monthly_cost": Decimal(0), "estimated_monthly_savings": Decimal(str(monthly)) if monthly else None,
                "savings_basis": "Savings amount reported by Azure Advisor.",
                "issue": (p.get("shortDescription", {}) or {}).get("problem") or "",
                "evidence": {"advisor_recommendation_id": rec.get("id"), "impact": p.get("impact"), "extended_properties": ext, "last_updated": p.get("lastUpdated")},
                "recommendation": (p.get("shortDescription", {}) or {}).get("solution") or "See Azure Advisor for details.",
                "evidence_source": "azure_advisor",
                "is_demo": False,
            }, created)
    return {"imported": len(created), "created_ids": created, "errors": errors}
