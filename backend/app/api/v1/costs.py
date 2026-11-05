from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import report_params
from app.core.db import get_db
from app.core.errors import NotFoundError, PermissionDenied
from app.models import CostComparison
from app.schemas.common import Envelope, SavedComparisonIn
from app.security.auth import CurrentUser, require
from app.services import export_service, resource_service
from app.services.params import ReportParams
from app.services.reporting_service import ReportingService

router = APIRouter(prefix="/costs", tags=["Cost Explorer & Comparison"])


@router.get("/explorer", response_model=Envelope, summary="Single query result shared by every chart type and the table")
def explorer(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).explorer()


@router.get("/compare", response_model=Envelope, summary="Period comparison with reconciled waterfall attribution")
def compare(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).compare()


@router.get("/trend", response_model=Envelope)
def trend(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).trend(include_budget=False)


@router.get("/grouped", response_model=Envelope, summary="Grouped costs (paged)")
def grouped(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params.copy(sort=params.sort if params.sort != "abs_diff" else "current_cost"), user.allowed_subscription_fks).contributors()


@router.get("/contributors", response_model=Envelope, summary="Cost change contributors (paged, sorted; default largest absolute change)")
def contributors(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return ReportingService(db, params, user.allowed_subscription_fks).contributors()


@router.get("/meter-comparison", response_model=Envelope, summary="What changed: meter-level price/volume decomposition")
def meter_comparison(params: ReportParams = Depends(report_params), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return resource_service.meter_comparison(db, params, user.allowed_subscription_fks)


@router.get("/records", response_model=Envelope, summary="Exact billing records behind the current view (paged)")
def records(
    params: ReportParams = Depends(report_params),
    include_comparison: bool = Query(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    return resource_service.billing_records(db, params, user.allowed_subscription_fks, include_comparison)


@router.get("/saved-comparisons", summary="Saved comparison views")
def list_saved(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [{"id": c.id, "name": c.name, "params": c.params, "created_by": c.created_by, "created_at": c.created_at.isoformat()}
            for c in db.execute(select(CostComparison).order_by(CostComparison.name)).scalars()]


@router.post("/saved-comparisons", status_code=201, summary="Save a comparison view (stores parameters, not results)")
def save_comparison(body: SavedComparisonIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    c = CostComparison(name=body.name, params=body.params, created_by=user.email or user.name)
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.delete("/saved-comparisons/{comparison_id}", status_code=204)
def delete_saved(comparison_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    c = db.get(CostComparison, comparison_id)
    if c is None:
        raise NotFoundError("Saved comparison not found")
    if c.created_by != (user.email or user.name) and not user.can("admin"):
        raise PermissionDenied("Only the owner or an administrator can delete this saved comparison")
    db.delete(c)
    db.commit()


@router.get("/export", summary="Download CSV / Excel for the current filters", response_class=Response)
def export(
    params: ReportParams = Depends(report_params),
    view: Literal["explorer", "compare", "contributors", "resources", "records"] = "explorer",
    format: Literal["csv", "xlsx"] = "csv",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("export")),
):
    name, content, media = export_service.build_export(db, params, view, format, user.allowed_subscription_fks)
    return Response(content=content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
