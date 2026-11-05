from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.comparison import money
from app.core.db import get_db
from app.core.errors import NotFoundError, ValidationFailed
from app.models import AzureResource, SavingsOpportunity
from app.schemas.common import Envelope, StatusUpdate
from app.security.auth import CurrentUser, require
from app.services import audit_service
from app.services.labels import LabelResolver
from app.services.savings_service import STATUSES

router = APIRouter(prefix="/savings", tags=["Potential Cost Savings"])


@router.get("", response_model=Envelope, summary="Evidence-based savings opportunities (estimates, never realised savings)")
def list_savings(
    status: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    application: list[int] = Query(default=[]),
    environment: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    labels = LabelResolver(db)
    q = select(SavingsOpportunity)
    if status:
        q = q.where(SavingsOpportunity.status.in_(status))
    if source:
        q = q.where(SavingsOpportunity.evidence_source.in_(source))
    if application:
        q = q.where(SavingsOpportunity.application_id.in_(application))
    if environment:
        ids = [e.id for e in labels.envs.values() if e.environment_group in environment or e.code in environment]
        q = q.where(SavingsOpportunity.environment_id.in_(ids or [-1]))
    if user.allowed_subscription_fks is not None:
        q = q.where(SavingsOpportunity.subscription_fk.in_(list(user.allowed_subscription_fks) or [-1]))
    rows = list(db.execute(q.order_by(SavingsOpportunity.estimated_monthly_savings.desc().nulls_last(), SavingsOpportunity.current_monthly_cost.desc())).scalars())
    ids = {r.resource_key: r.id for r in db.execute(select(AzureResource).where(AzureResource.resource_key.in_([o.resource_key for o in rows if o.resource_key]))).scalars()}
    data = []
    for o in rows:
        app_key, app = labels.application(o.application_id, None) if o.application_id is not None else ("", "—")
        _, env = labels.environment(o.environment_id) if o.environment_id is not None else ("", "—")
        _, sub = labels.subscription(o.subscription_fk) if o.subscription_fk is not None else ("", "—")
        data.append({
            "id": o.id, "rule_code": o.rule_code, "title": o.title, "resource_name": o.resource_name, "resource_key": o.resource_key,
            "resource_id": ids.get(o.resource_key), "application": app, "environment": env, "subscription_name": sub,
            "service_category": o.service_category, "currency": o.billing_currency, "current_monthly_cost": money(o.current_monthly_cost),
            "estimated_monthly_savings": money(o.estimated_monthly_savings), "savings_basis": o.savings_basis, "issue": o.issue,
            "evidence": o.evidence, "recommendation": o.recommendation, "evidence_source": o.evidence_source, "status": o.status,
            "detected_at": o.detected_at.isoformat(), "last_evaluated_at": o.last_evaluated_at.isoformat(), "is_demo": o.is_demo,
        })
    open_total = sum((r["estimated_monthly_savings"] or 0) for r in data if r["status"] in ("open", "investigating", "accepted"))
    return {"data": data, "meta": {"total": len(data), "open_estimated_monthly_savings": round(open_total, 2),
                                   "note": "Estimated potential savings. Not realised savings. No resource is modified by this platform."}}


@router.post("/{opportunity_id}/status")
def set_status(opportunity_id: int, body: StatusUpdate, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_savings"))):
    if body.status not in STATUSES:
        raise ValidationFailed(f"status must be one of {STATUSES}")
    o = db.get(SavingsOpportunity, opportunity_id)
    if o is None:
        raise NotFoundError("Opportunity not found")
    prev = o.status
    o.status = body.status
    audit_service.record(db, user, "savings.status", entity_type="savings_opportunity", entity_id=str(o.id), details={"from": prev, "to": body.status, "comment": body.comment}, request=request)
    db.commit()
    return {"id": o.id, "status": o.status}


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    q = select(SavingsOpportunity.evidence_source, SavingsOpportunity.status, func.count(), func.coalesce(func.sum(SavingsOpportunity.estimated_monthly_savings), 0))
    if user.allowed_subscription_fks is not None:
        q = q.where(SavingsOpportunity.subscription_fk.in_(list(user.allowed_subscription_fks) or [-1]))
    rows = db.execute(q.group_by(SavingsOpportunity.evidence_source, SavingsOpportunity.status)).all()
    return [{"source": r[0], "status": r[1], "count": r[2], "estimated_monthly_savings": money(r[3])} for r in rows]
