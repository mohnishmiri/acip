"""Budgets, budget utilisation and forecasts."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import periods as P
from app.analytics.comparison import ZERO, money, pct_out
from app.core.errors import NotFoundError, ValidationFailed
from app.forecasting.forecast import METHODS, budget_status, forecast_period
from app.models import Budget
from app.repositories.cost_repository import CostFilters, CostRepository
from app.services import settings_service
from app.services.labels import LabelResolver

SCOPE_TYPES = ("total", "application", "subscription", "environment", "resource_group")


def monthly_amount(budget: Budget, d: date) -> Decimal:
    return Decimal(budget.amount) if budget.period_type == "monthly" else Decimal(budget.amount) / Decimal(12)


def daily_amount(budget: Budget, d: date) -> Decimal:
    return monthly_amount(budget, d) / Decimal(calendar.monthrange(d.year, d.month)[1])


def _active(b: Budget, d: date) -> bool:
    return b.enabled and b.start_date <= d and (b.end_date is None or b.end_date >= d)


def find_scope_budget(db: Session, f: CostFilters, labels: LabelResolver, as_of: date) -> Budget | None:
    """Pick the budget that matches the current filter context exactly (if any)."""
    budgets = [b for b in db.execute(select(Budget)).scalars() if _active(b, as_of) and b.currency == f.currency and b.cost_type == f.dataset_type]
    other_filters = any([f.service_categories, f.regions, f.resource_keys, f.resource_types, f.owners, f.cost_centers,
                         f.meter_categories, f.meter_names, f.skus, f.tags, f.search, f.charge_types, f.pricing_models])
    if other_filters:
        return None
    scope_type, ref = None, None
    if f.subscription_fks and len(f.subscription_fks) == 1 and not (f.application_ids or f.environment_ids or f.resource_groups):
        scope_type, ref = "subscription", labels.subs[f.subscription_fks[0]].subscription_id
    elif f.application_ids and len(f.application_ids) == 1 and not (f.subscription_fks or f.environment_ids or f.resource_groups or f.allocation_statuses):
        scope_type, ref = "application", str(f.application_ids[0])
    elif f.environment_ids and not (f.subscription_fks or f.application_ids or f.resource_groups):
        ids = set(f.environment_ids)
        for group in ("production", "non_production", "shared", "unallocated"):
            if ids == {e.id for e in labels.envs.values() if e.environment_group == group}:
                scope_type, ref = "environment", group
    elif f.resource_groups and len(f.resource_groups) == 1 and not (f.application_ids or f.environment_ids):
        scope_type, ref = "resource_group", f.resource_groups[0]
    elif not (f.subscription_fks or f.application_ids or f.environment_ids or f.resource_groups or f.allocation_statuses):
        scope_type = "total"
    if scope_type is None:
        return None
    matches = [b for b in budgets if b.scope_type == scope_type and (scope_type == "total" or (b.scope_ref or "").lower() == (ref or "").lower())]
    matches.sort(key=lambda b: (0 if b.period_type == "monthly" else 1, b.id))
    return matches[0] if matches else None


def filters_for_budget(db: Session, b: Budget, labels: LabelResolver, allowed: set[int] | None = None) -> CostFilters:
    f = CostFilters(dataset_type=b.cost_type, currency=b.currency, allowed_subscription_fks=allowed)
    if b.scope_type == "application":
        f.application_ids = [int(b.scope_ref)] if b.scope_ref and b.scope_ref.isdigit() else [-1]
    elif b.scope_type == "subscription":
        s = labels.sub_by_guid.get((b.scope_ref or "").lower())
        f.subscription_fks = [s.id] if s else [-1]
    elif b.scope_type == "environment":
        f.environment_ids = [e.id for e in labels.envs.values() if e.environment_group == b.scope_ref or e.code == b.scope_ref] or [-1]
    elif b.scope_type == "resource_group":
        f.resource_groups = [(b.scope_ref or "").lower()]
    return f


def scope_label(b: Budget, labels: LabelResolver) -> str:
    if b.scope_type == "total":
        return "All subscriptions"
    if b.scope_type == "application":
        app = labels.apps.get(int(b.scope_ref)) if b.scope_ref and b.scope_ref.isdigit() else None
        return app.name if app else f"Application {b.scope_ref}"
    if b.scope_type == "subscription":
        s = labels.sub_by_guid.get((b.scope_ref or "").lower())
        return s.subscription_name if s else (b.scope_ref or "")
    if b.scope_type == "environment":
        return {"production": "Production", "non_production": "Non-Production", "shared": "Shared Services", "unallocated": "Unallocated"}.get(b.scope_ref or "", b.scope_ref or "")
    return f"Resource group {b.scope_ref}"


def evaluate_budget(db: Session, b: Budget, labels: LabelResolver, *, method: str | None = None, allowed: set[int] | None = None) -> dict[str, Any]:
    ws = settings_service.week_start(db)
    repo = CostRepository(db, ws)
    f = filters_for_budget(db, b, labels, allowed)
    _, data_end = repo.date_bounds(f)
    as_of = settings_service.complete_through(db, data_end) or date.today()
    if b.period_type == "monthly":
        ps, pe = P.month_start(as_of), P.month_end(as_of)
    else:
        ps, pe = date(as_of.year, 1, 1), date(as_of.year, 12, 31)
    method = method or settings_service.get_setting(db, "forecast.default_method")
    hist = repo.daily_totals(f, min(ps, as_of - timedelta(days=89)), as_of)
    fc = forecast_period(hist, as_of=as_of, period_start=ps, period_end=pe, method=method)
    amount = Decimal(b.amount)
    st = budget_status(amount, fc.actual_to_date, fc.forecast_total)
    util = st["utilization_pct"]
    crossed = [t for t in (b.thresholds or []) if util is not None and util >= Decimal(str(t))]
    elapsed = max(fc.elapsed_days, 1)
    return {
        "id": b.id,
        "name": b.name,
        "scope_type": b.scope_type,
        "scope_ref": b.scope_ref,
        "scope_label": scope_label(b, labels),
        "period_type": b.period_type,
        "period_start": ps.isoformat(),
        "period_end": pe.isoformat(),
        "as_of": as_of.isoformat(),
        "currency": b.currency,
        "cost_type": b.cost_type,
        "amount": money(amount),
        "actual": money(fc.actual_to_date),
        "remaining": money(st["remaining"]),
        "utilization_pct": pct_out(util),
        "forecast": money(fc.forecast_total),
        "forecast_method": fc.method,
        "forecast_method_label": fc.method_label,
        "forecast_variance": money(st["forecast_variance"]),
        "forecast_utilization_pct": pct_out(st["forecast_utilization_pct"]),
        "daily_run_rate": money(fc.actual_to_date / Decimal(elapsed)),
        "elapsed_days": fc.elapsed_days,
        "remaining_days": fc.remaining_days,
        "thresholds": b.thresholds,
        "thresholds_crossed": crossed,
        "forecast_exceeds_budget": bool(st["forecast_variance"] is not None and st["forecast_variance"] > ZERO),
        "forecast_alert": b.forecast_alert,
        "enabled": b.enabled,
        "start_date": b.start_date.isoformat(),
        "end_date": b.end_date.isoformat() if b.end_date else None,
        "notes": b.notes,
        "is_demo": b.is_demo,
        "forecast_notes": fc.notes,
    }


def list_budgets(db: Session, allowed: set[int] | None = None) -> list[dict[str, Any]]:
    labels = LabelResolver(db)
    out = []
    for b in db.execute(select(Budget).order_by(Budget.scope_type, Budget.name)).scalars():
        if allowed is not None and b.scope_type == "total":
            continue  # scoped users only see budgets for their own scope
        out.append(evaluate_budget(db, b, labels, allowed=allowed))
    return out


def validate_budget_payload(db: Session, data: dict[str, Any]) -> None:
    labels = LabelResolver(db)
    st = data.get("scope_type")
    if st not in SCOPE_TYPES:
        raise ValidationFailed(f"scope_type must be one of {SCOPE_TYPES}")
    ref = data.get("scope_ref")
    if st == "total":
        data["scope_ref"] = None
    elif not ref:
        raise ValidationFailed("scope_ref is required for this scope type")
    elif st == "application" and not (str(ref).isdigit() and int(ref) in labels.apps):
        raise ValidationFailed("scope_ref must be an existing application id")
    elif st == "subscription" and str(ref).lower() not in labels.sub_by_guid:
        raise ValidationFailed("scope_ref must be a registered subscription id")
    elif st == "environment" and ref not in ("production", "non_production", "shared", "unallocated"):
        raise ValidationFailed("scope_ref must be production, non_production, shared or unallocated")
    if data.get("period_type") not in ("monthly", "annual"):
        raise ValidationFailed("period_type must be monthly or annual")
    if Decimal(str(data.get("amount", 0))) <= 0:
        raise ValidationFailed("amount must be greater than zero")
    if data.get("cost_type", "actual") not in ("actual", "amortized"):
        raise ValidationFailed("cost_type must be actual or amortized")
    th = data.get("thresholds") or [70, 80, 90, 100]
    if any(not (0 < float(t) <= 500) for t in th):
        raise ValidationFailed("thresholds must be percentages between 0 and 500")
    data["thresholds"] = sorted({float(t) for t in th})


def get_budget(db: Session, budget_id: int) -> Budget:
    b = db.get(Budget, budget_id)
    if b is None:
        raise NotFoundError(f"Budget {budget_id} not found")
    return b


def forecast_methods() -> dict[str, str]:
    return METHODS
