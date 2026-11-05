from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import report_params
from app.api.v1.anomalies import anomaly_summary
from app.core.db import get_db
from app.schemas.common import Envelope
from app.security.auth import CurrentUser, require
from app.services import resource_service
from app.services.params import ReportParams

router = APIRouter(prefix="/resources", tags=["Resource Analysis"])


@router.get("", response_model=Envelope, summary="Resources with period comparison (server-side paged/sorted/searched)")
def list_resources(
    params: ReportParams = Depends(report_params),
    sort_dir: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    return resource_service.list_resources(db, params, user.allowed_subscription_fks, sort_dir)


@router.get("/{resource_id}", response_model=Envelope)
def resource_detail(resource_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return resource_service.resource_detail(db, resource_id, params, user.allowed_subscription_fks)


@router.get("/{resource_id}/history", response_model=Envelope, summary="Daily (90d) and monthly (13m) cost; usage quantity by meter")
def resource_history(resource_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return resource_service.resource_history(db, resource_id, params, user.allowed_subscription_fks)


@router.get("/{resource_id}/meters", response_model=Envelope, summary="Meter-level comparison and root-cause decomposition")
def resource_meters(resource_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return resource_service.resource_meters(db, resource_id, params, user.allowed_subscription_fks)


@router.get("/{resource_id}/records", response_model=Envelope, summary="Billing records for the resource")
def resource_records(
    resource_id: int,
    params: ReportParams = Depends(report_params),
    include_comparison: bool = Query(True),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    from app.services.resource_service import _resource_or_404

    r = _resource_or_404(db, resource_id)
    return resource_service.billing_records(db, params.copy(resource=[r.resource_key]), user.allowed_subscription_fks, include_comparison)


@router.get("/{resource_id}/anomalies", response_model=Envelope)
def resource_anomalies(resource_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    rows = resource_service.resource_anomalies(db, resource_id, user.allowed_subscription_fks)
    from app.services.labels import LabelResolver

    labels = LabelResolver(db)
    return {"data": [anomaly_summary(a, labels) for a in rows], "meta": {"total": len(rows)}}


@router.get("/{resource_id}/activity", summary="Optional Azure Activity Log evidence (configuration changes)")
def resource_activity(resource_id: int, params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return resource_service.resource_activity(db, resource_id, params, user.allowed_subscription_fks)
