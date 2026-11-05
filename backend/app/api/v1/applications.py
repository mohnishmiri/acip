from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import report_params
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.schemas.common import Envelope
from app.security.auth import CurrentUser, require
from app.services import application_service
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService

router = APIRouter(prefix="/applications", tags=["Application Cost Allocation"])


@router.get("", response_model=Envelope, summary="Application summary: prod / non-prod, budget, run rate, forecast, YTD, 30-day change")
def applications(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return application_service.application_summary(db, params, user.allowed_subscription_fks)


@router.get("/{application_id}", response_model=Envelope)
def application(application_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    if user.scoped_application_ids is not None and application_id not in user.scoped_application_ids:
        raise NotFoundError("Application not found")
    return application_service.application_detail(db, application_id, params, user.allowed_subscription_fks)


@router.get("/{application_id}/costs", response_model=Envelope, summary="Explorer result scoped to one application")
def application_costs(application_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    if user.scoped_application_ids is not None and application_id not in user.scoped_application_ids:
        raise NotFoundError("Application not found")
    return ReportingService(db, params.copy(application=[str(application_id)]), user.allowed_subscription_fks).explorer()
