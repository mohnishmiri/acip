from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.comparison import sort_items
from app.api.deps import report_params
from app.core.db import get_db
from app.schemas.common import Envelope
from app.security.auth import CurrentUser, require
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService, item_out

router = APIRouter(prefix="/dashboard", tags=["Executive Overview"])


@router.get("/overview", response_model=Envelope, summary="KPI cards (actuals, budget, forecast, savings)")
def overview(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).overview()


@router.get("/trends", response_model=Envelope, summary="Cost trend with previous period, budget and forecast lines")
def trends(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).trend()


def _breakdown(dim: str, params: ReportParams, db: Session, user: CurrentUser):
    svc = ReportingService(db, params.copy(group_by=dim), user.allowed_subscription_fks)
    scope = svc.scope()
    items, (tp, tc, _) = svc.compared_groups(scope, dim)
    has_cmp = scope.comparison is not None
    return {
        "data": {"group_by": dim, "totals": svc.totals_out(scope, tp, tc), "groups": [item_out(i, has_cmp) for i in sort_items(items, "current_cost")]},
        "meta": svc.meta(scope),
    }


@router.get("/service-breakdown", response_model=Envelope)
def service_breakdown(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return _breakdown("service_category", params, db, user)


@router.get("/application-breakdown", response_model=Envelope)
def application_breakdown(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return _breakdown("application", params, db, user)


@router.get("/environment-breakdown", response_model=Envelope)
def environment_breakdown(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return _breakdown("environment", params, db, user)


@router.get("/subscription-breakdown", response_model=Envelope)
def subscription_breakdown(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return _breakdown("subscription", params, db, user)
