"""Application cost allocation summary."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import periods as P
from app.analytics.comparison import ZERO, money, pct_change, pct_out
from app.core.errors import NotFoundError
from app.forecasting.forecast import forecast_period
from app.models import Application, CostAnomaly, SavingsOpportunity
from app.repositories.cost_repository import CostFilters
from app.services import budget_service, settings_service
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService


def application_summary(db: Session, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    svc = ReportingService(db, params, allowed)
    scope = svc.scope()
    f = scope.filters
    repo = svc.repo
    a = scope.as_of
    labels = svc.labels
    method = settings_service.get_setting(db, "forecast.default_method")

    rows = repo.grouped_compare(f, scope.current.period, scope.comparison, ["application", "environment"])
    ytd = P.resolve_period("year_to_date", a)
    ytd_ly = P.resolve_comparison(ytd, "same_period_last_year")
    ytd_rows = repo.grouped_compare(f, ytd.period, ytd_ly, ["application"])
    l30 = P.Period(a - timedelta(days=29), a)
    p30 = P.Period(a - timedelta(days=59), a - timedelta(days=30))
    r30 = repo.grouped_compare(f, l30, p30, ["application"])
    hist = repo.series(f, P.Period(a - timedelta(days=89), a), "daily", ["application"])
    ms, me = P.month_start(a), P.month_end(a)

    def key_of(values: dict[str, Any]) -> str:
        return labels.application(values.get("application_id"), values.get("allocation_status"))[0]

    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"prod": ZERO, "nonprod": ZERO, "other_env": ZERO, "current": ZERO, "previous": ZERO})
    for r in rows:
        k = key_of(r.values)
        env = labels.envs.get(r.values.get("environment_id"))
        grp = env.environment_group if env else "unallocated"
        agg[k]["current"] += r.current
        agg[k]["previous"] += r.previous
        if grp == "production":
            agg[k]["prod"] += r.current
        elif grp == "non_production":
            agg[k]["nonprod"] += r.current
        else:
            agg[k]["other_env"] += r.current
    ytd_map = {key_of(r.values): r for r in ytd_rows}
    r30_map = {key_of(r.values): r for r in r30}
    daily: dict[str, dict] = defaultdict(dict)
    for r in hist:
        k = key_of(r)
        daily[k][r["bucket"]] = daily[k].get(r["bucket"], ZERO) + Decimal(r["cost"])

    savings_by_app = {
        (row[0] if row[0] is not None else "unallocated"): row[1]
        for row in db.execute(
            select(SavingsOpportunity.application_id, func.sum(SavingsOpportunity.estimated_monthly_savings))
            .where(SavingsOpportunity.status.in_(["open", "investigating", "accepted"]), SavingsOpportunity.billing_currency == scope.currency)
            .group_by(SavingsOpportunity.application_id)
        )
    }
    anomalies_by_app = {
        row[0]: row[1]
        for row in db.execute(
            select(CostAnomaly.application_id, func.count()).where(CostAnomaly.status.in_(["open", "investigating"])).group_by(CostAnomaly.application_id)
        )
    }

    keys = list(dict.fromkeys([str(app.id) for app in sorted(labels.apps.values(), key=lambda x: x.sort_order)] + list(agg.keys())))
    out = []
    for k in keys:
        if k not in agg and k not in ytd_map:
            if not k.isdigit():
                continue
        v = agg.get(k, {"prod": ZERO, "nonprod": ZERO, "other_env": ZERO, "current": ZERO, "previous": ZERO})
        if k.isdigit():
            app_id = int(k)
            name = labels.apps[app_id].name if app_id in labels.apps else k
            bf = CostFilters(dataset_type=f.dataset_type, currency=f.currency, application_ids=[app_id])
            budget = budget_service.find_scope_budget(db, bf, labels, a)
        else:
            app_id, name, budget = None, ("Shared Services" if k == "shared" else "Unallocated"), None
        fc = forecast_period(daily.get(k, {}), as_of=a, period_start=ms, period_end=me, method=method)
        budget_amt = budget_service.monthly_amount(budget, a) if budget else None
        run_rate = (fc.actual_to_date / Decimal(fc.elapsed_days) * Decimal((me - ms).days + 1)) if fc.elapsed_days else ZERO
        y = ytd_map.get(k)
        t = r30_map.get(k)
        out.append({
            "key": k,
            "application_id": app_id,
            "name": name,
            "is_shared": k == "shared",
            "is_unallocated": k == "unallocated",
            "production": money(v["prod"]),
            "non_production": money(v["nonprod"]),
            "other_environments": money(v["other_env"]),
            "current": money(v["current"]),
            "previous": money(v["previous"]) if scope.comparison else None,
            "diff": money(v["current"] - v["previous"]) if scope.comparison else None,
            "pct": pct_out(pct_change(v["previous"], v["current"])) if scope.comparison else None,
            "budget": money(budget_amt),
            "budget_name": budget.name if budget else None,
            "month_to_date": money(fc.actual_to_date),
            "run_rate": money(run_rate),
            "forecast": money(fc.forecast_total),
            "expected_variance": money(fc.forecast_total - budget_amt) if budget_amt is not None else None,
            "budget_utilization_pct": pct_out(fc.actual_to_date / budget_amt * 100) if budget_amt else None,
            "ytd_actual": money(y.current) if y else 0.0,
            "ytd_previous_year": money(y.previous) if y else 0.0,
            "ytd_growth_pct": pct_out(pct_change(y.previous, y.current)) if y else None,
            "change_30d": money(t.current - t.previous) if t else None,
            "change_30d_pct": pct_out(pct_change(t.previous, t.current)) if t else None,
            "potential_savings": money(Decimal(savings_by_app.get(app_id if app_id is not None else "unallocated") or 0)),
            "open_anomalies": anomalies_by_app.get(app_id, 0) if app_id is not None else 0,
        })
    return {"data": out, "meta": svc.meta(scope, forecast_method=method, month=[ms.isoformat(), me.isoformat()])}


def application_detail(db: Session, application_id: int, params: ReportParams, allowed: set[int] | None) -> dict[str, Any]:
    app = db.get(Application, application_id)
    if app is None:
        raise NotFoundError(f"Application {application_id} not found")
    p = params.copy(application=[str(application_id)])
    svc = ReportingService(db, p, allowed)
    scope = svc.scope()
    subs = [s for s in svc.labels.subs.values() if s.application_id == application_id and (allowed is None or s.id in allowed)]
    by_env, (tp, tc, _) = svc.compared_groups(scope, "environment")
    by_sub, _ = svc.compared_groups(scope, "subscription")
    by_service, _ = svc.compared_groups(scope, "service_category")
    by_rg, _ = svc.compared_groups(scope, "resource_group")
    from app.analytics.comparison import sort_items
    from app.services.reporting_service import item_out

    top_resources = ReportingService(db, p.copy(group_by="resource", page=1, page_size=10, sort="current_cost"), allowed).contributors()["data"]
    top_movers = ReportingService(db, p.copy(group_by="resource", page=1, page_size=10, sort="abs_diff"), allowed).contributors()["data"]
    budget = budget_service.find_scope_budget(db, CostFilters(dataset_type=scope.filters.dataset_type, currency=scope.currency, application_ids=[application_id]), svc.labels, scope.as_of)
    budget_status = budget_service.evaluate_budget(db, budget, svc.labels, allowed=allowed) if budget else None
    anomalies = db.execute(
        select(CostAnomaly).where(CostAnomaly.application_id == application_id).order_by(CostAnomaly.detection_date.desc()).limit(10)
    ).scalars()
    savings = db.execute(select(SavingsOpportunity).where(SavingsOpportunity.application_id == application_id)).scalars()
    return {
        "data": {
            "application": {"id": app.id, "code": app.code, "name": app.name, "description": app.description, "owner": app.owner},
            "subscriptions": [{"subscription_id": s.subscription_id, "subscription_name": s.subscription_name,
                               "environment": svc.labels.environment(s.environment_id)[1], "enabled": s.enabled} for s in subs],
            "totals": svc.totals_out(scope, tp, tc),
            "by_environment": [item_out(i) for i in sort_items(by_env, "current_cost")],
            "by_subscription": [item_out(i) for i in sort_items(by_sub, "current_cost")],
            "by_service": [item_out(i) for i in sort_items(by_service, "current_cost")],
            "by_resource_group": [item_out(i) for i in sort_items(by_rg, "current_cost")][:25],
            "top_resources": top_resources,
            "top_movers": top_movers,
            "budget": budget_status,
            "anomalies": [{"id": x.id, "title": x.title, "severity": x.severity, "status": x.status, "detection_date": x.detection_date.isoformat(),
                           "absolute_increase": money(x.absolute_increase)} for x in anomalies],
            "savings": [{"id": s.id, "title": s.title, "estimated_monthly_savings": money(s.estimated_monthly_savings), "status": s.status} for s in savings],
        },
        "meta": svc.meta(scope),
    }
