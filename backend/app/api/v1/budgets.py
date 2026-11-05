from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.analytics import periods as P
from app.analytics.comparison import money
from app.api.deps import report_params
from app.core.db import get_db
from app.forecasting.forecast import METHODS, forecast_period
from app.models import Budget
from app.schemas.common import BudgetIn, Envelope
from app.security.auth import CurrentUser, require
from app.services import audit_service, budget_service, settings_service
from app.services.labels import LabelResolver
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService

router = APIRouter(tags=["Budget & Forecast"])


@router.get("/budgets", response_model=Envelope, summary="Budgets with utilisation, remaining, forecast and thresholds")
def list_budgets(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return {"data": budget_service.list_budgets(db, user.allowed_subscription_fks), "meta": {"forecast_methods": METHODS}}


@router.post("/budgets", status_code=201, summary="Create a budget")
def create_budget(body: BudgetIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_budgets"))):
    data = body.model_dump()
    budget_service.validate_budget_payload(db, data)
    b = Budget(**data, created_by=user.email or user.name)
    db.add(b)
    db.flush()
    audit_service.record(db, user, "budget.create", entity_type="budget", entity_id=str(b.id), details={**data, "amount": str(data["amount"]), "start_date": str(data["start_date"]), "end_date": str(data["end_date"])}, request=request)
    db.commit()
    return budget_service.evaluate_budget(db, b, LabelResolver(db))


@router.put("/budgets/{budget_id}", summary="Update a budget")
def update_budget(budget_id: int, body: BudgetIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_budgets"))):
    b = budget_service.get_budget(db, budget_id)
    data = body.model_dump()
    budget_service.validate_budget_payload(db, data)
    for k, v in data.items():
        setattr(b, k, v)
    audit_service.record(db, user, "budget.update", entity_type="budget", entity_id=str(b.id), request=request)
    db.commit()
    return budget_service.evaluate_budget(db, b, LabelResolver(db))


@router.delete("/budgets/{budget_id}", status_code=204, summary="Delete a budget")
def delete_budget(budget_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_budgets"))):
    b = budget_service.get_budget(db, budget_id)
    db.delete(b)
    audit_service.record(db, user, "budget.delete", entity_type="budget", entity_id=str(budget_id), request=request)
    db.commit()


@router.get("/forecasts", response_model=Envelope, summary="Month-end forecast for the current filters with all methods")
def forecasts(
    params: ReportParams = Depends(report_params),
    method: str | None = Query(None, pattern="^(run_rate|recent|trend)$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    svc = ReportingService(db, params, user.allowed_subscription_fks)
    scope = svc.scope()
    a = scope.as_of
    ms, me = P.month_start(a), P.month_end(a)
    hist = svc.repo.daily_totals(scope.filters, a - timedelta(days=119), a)
    results = {}
    for m in METHODS:
        fc = forecast_period(hist, as_of=a, period_start=ms, period_end=me, method=m)
        results[m] = {
            "method": m, "label": fc.method_label, "actual_to_date": money(fc.actual_to_date), "projected_remaining": money(fc.projected_remaining),
            "forecast_total": money(fc.forecast_total), "daily_rate": money(fc.daily_rate), "elapsed_days": fc.elapsed_days,
            "remaining_days": fc.remaining_days, "notes": fc.notes,
            "projection": [{"date": d.isoformat(), "value": money(v)} for d, v in fc.projection],
        }
    selected = method or settings_service.get_setting(db, "forecast.default_method")
    yr_start, yr_end = date(a.year, 1, 1), date(a.year, 12, 31)
    annual = forecast_period(svc.repo.daily_totals(scope.filters, yr_start, a), as_of=a, period_start=yr_start, period_end=yr_end, method=selected)
    actual_series = [{"date": d.isoformat(), "value": money(hist.get(d, 0))} for d in (ms + timedelta(days=i) for i in range((a - ms).days + 1))]
    budget = budget_service.find_scope_budget(db, scope.filters, svc.labels, a)
    return {
        "data": {
            "month": {"start": ms.isoformat(), "end": me.isoformat()},
            "selected_method": selected,
            "methods": results,
            "actual_series": actual_series,
            "annual": {"actual_to_date": money(annual.actual_to_date), "forecast_total": money(annual.forecast_total), "method": annual.method_label},
            "budget": {"name": budget.name, "monthly_amount": money(budget_service.monthly_amount(budget, a))} if budget else None,
            "disclaimer": "Forecasts are projections based on billed history and are not actual Azure charges.",
        },
        "meta": svc.meta(scope),
    }
