from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.analytics.comparison import money, pct_out
from app.core.db import get_db
from app.core.errors import NotFoundError, ValidationFailed
from app.models import AnomalyEvent, AnomalyRule, AzureResource, CostAnomaly
from app.schemas.common import AnomalyRuleUpdate, CommentIn, Envelope, StatusUpdate
from app.security.auth import CurrentUser, require
from app.services import audit_service
from app.services.labels import LabelResolver

router = APIRouter(prefix="/anomalies", tags=["Cost Anomalies"])
STATUSES = ("open", "investigating", "acknowledged", "resolved", "dismissed", "expected")


def anomaly_summary(a: CostAnomaly, labels: LabelResolver) -> dict[str, Any]:
    app_key, app_name = labels.application(a.application_id, None) if a.application_id is not None else ("", "—")
    env_code, env_name = labels.environment(a.environment_id) if a.environment_id is not None else ("", "—")
    sub_guid, sub_name = labels.subscription(a.subscription_fk) if a.subscription_fk is not None else ("", "—")
    return {
        "id": a.id,
        "anomaly_ref": f"ANM-{a.id:06d}",
        "title": a.title,
        "rule_code": a.rule_code,
        "detection_type": a.detection_type,
        "category": a.category,
        "scope_level": a.scope_level,
        "detected_at": a.detected_at.isoformat(),
        "detection_date": a.detection_date.isoformat(),
        "last_detected_date": a.last_detected_date.isoformat(),
        "period_start": a.period_start.isoformat(),
        "period_end": a.period_end.isoformat(),
        "application_id": a.application_id,
        "application": app_name,
        "environment": env_name,
        "environment_code": env_code,
        "subscription_id": sub_guid,
        "subscription_name": sub_name,
        "service_category": a.service_category,
        "resource_group": a.resource_group,
        "resource_key": a.resource_key,
        "resource_name": a.resource_name,
        "previous_cost": money(a.previous_cost),
        "current_cost": money(a.current_cost),
        "expected_baseline": money(a.expected_baseline),
        "absolute_increase": money(a.absolute_increase),
        "percentage_increase": pct_out(a.percentage_increase),
        "severity": a.severity,
        "status": a.status,
        "occurrence_count": a.occurrence_count,
        "currency": a.billing_currency,
        "cost_type": a.dataset_type,
        "is_demo": a.is_demo,
    }


@router.get("", response_model=Envelope, summary="Anomalies (filter, sort, page)")
def list_anomalies(
    status: list[str] = Query(default=[]),
    severity: list[str] = Query(default=[]),
    rule_code: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    application: list[int] = Query(default=[]),
    environment: list[str] = Query(default=[]),
    subscription: list[str] = Query(default=[]),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    sort: str = Query("severity", pattern="^(severity|detection_date|absolute_increase|percentage_increase)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    labels = LabelResolver(db)
    q = select(CostAnomaly)
    if status:
        q = q.where(CostAnomaly.status.in_(status))
    if severity:
        q = q.where(CostAnomaly.severity.in_(severity))
    if rule_code:
        q = q.where(CostAnomaly.rule_code.in_(rule_code))
    if category:
        q = q.where(CostAnomaly.category.in_(category))
    if application:
        q = q.where(CostAnomaly.application_id.in_(application))
    if environment:
        ids = [e.id for e in labels.envs.values() if e.environment_group in environment or e.code in environment]
        q = q.where(CostAnomaly.environment_id.in_(ids or [-1]))
    if subscription:
        fks = [labels.sub_by_guid[s.lower()].id for s in subscription if s.lower() in labels.sub_by_guid]
        q = q.where(CostAnomaly.subscription_fk.in_(fks or [-1]))
    if user.allowed_subscription_fks is not None:
        q = q.where(CostAnomaly.subscription_fk.in_(list(user.allowed_subscription_fks) or [-1]))
    if date_from:
        q = q.where(CostAnomaly.last_detected_date >= date_from)
    if date_to:
        q = q.where(CostAnomaly.detection_date <= date_to)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(func.lower(CostAnomaly.title).like(like), func.lower(func.coalesce(CostAnomaly.resource_name, "")).like(like)))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    sev_order = func.array_position(["critical", "high", "medium", "low", "informational"], CostAnomaly.severity)
    order = {
        "severity": [sev_order, CostAnomaly.absolute_increase.desc()],
        "detection_date": [CostAnomaly.last_detected_date.desc(), sev_order],
        "absolute_increase": [CostAnomaly.absolute_increase.desc()],
        "percentage_increase": [CostAnomaly.percentage_increase.desc().nulls_last()],
    }[sort]
    rows = db.execute(q.order_by(*order, CostAnomaly.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    counts_q = select(CostAnomaly.severity, func.count()).where(CostAnomaly.status.in_(["open", "investigating", "acknowledged"]))
    if user.allowed_subscription_fks is not None:
        counts_q = counts_q.where(CostAnomaly.subscription_fk.in_(list(user.allowed_subscription_fks) or [-1]))
    counts = dict(db.execute(counts_q.group_by(CostAnomaly.severity)).all())
    return {"data": [anomaly_summary(a, labels) for a in rows], "meta": {"page": page, "page_size": page_size, "total": total, "open_by_severity": counts}}


@router.get("/rules", summary="Anomaly detection rules")
def list_rules(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [
        {"id": r.id, "code": r.code, "name": r.name, "description": r.description, "detection_type": r.detection_type,
         "scope_level": r.scope_level, "filters": r.filters, "params": r.params, "enabled": r.enabled}
        for r in db.execute(select(AnomalyRule).order_by(AnomalyRule.id)).scalars()
    ]


@router.put("/rules/{rule_id}", summary="Update an anomaly rule's thresholds / filters")
def update_rule(rule_id: int, body: AnomalyRuleUpdate, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_alerts"))):
    r = db.get(AnomalyRule, rule_id)
    if r is None:
        raise NotFoundError("Rule not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    audit_service.record(db, user, "anomaly_rule.update", entity_type="anomaly_rule", entity_id=str(rule_id), details=body.model_dump(exclude_none=True), request=request)
    db.commit()
    return {"id": r.id, "code": r.code, "enabled": r.enabled, "params": r.params, "filters": r.filters}


def _get(db: Session, anomaly_id: int, user: CurrentUser) -> CostAnomaly:
    a = db.get(CostAnomaly, anomaly_id)
    if a is None or (user.allowed_subscription_fks is not None and a.subscription_fk not in user.allowed_subscription_fks):
        raise NotFoundError(f"Anomaly {anomaly_id} not found")
    return a


@router.get("/{anomaly_id}", response_model=Envelope, summary="Anomaly with evidence, trend, contributors and history")
def get_anomaly(anomaly_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    a = _get(db, anomaly_id, user)
    labels = LabelResolver(db)
    out = anomaly_summary(a, labels)
    res = db.execute(select(AzureResource).where(AzureResource.resource_key == a.resource_key)).scalar_one_or_none() if a.resource_key else None
    out.update(
        evidence=a.evidence,
        explanation=a.explanation,
        recommended_steps=a.recommended_steps,
        resource_id=res.id if res else None,
        resource_arm_id=res.resource_id if res else None,
        events=[
            {"id": e.id, "event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status, "comment": e.comment,
             "actor": e.actor, "details": e.details, "created_at": e.created_at.isoformat()}
            for e in db.execute(select(AnomalyEvent).where(AnomalyEvent.anomaly_id == a.id).order_by(AnomalyEvent.created_at.desc())).scalars()
        ],
        explanation_note="The explanation states measured billing facts only. Suggested investigation steps are not confirmed causes.",
    )
    return {"data": out, "meta": {}}


@router.post("/{anomaly_id}/status", summary="Update investigation status (with optional comment)")
def set_status(anomaly_id: int, body: StatusUpdate, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_anomalies"))):
    if body.status not in STATUSES:
        raise ValidationFailed(f"status must be one of {STATUSES}")
    a = _get(db, anomaly_id, user)
    prev = a.status
    a.status = body.status
    db.add(AnomalyEvent(anomaly_id=a.id, event_type="status_change", from_status=prev, to_status=body.status, comment=body.comment, actor=user.email or user.name))
    audit_service.record(db, user, "anomaly.status", entity_type="anomaly", entity_id=str(a.id), details={"from": prev, "to": body.status}, request=request)
    db.commit()
    return {"id": a.id, "status": a.status}


@router.post("/{anomaly_id}/comments", summary="Add an investigation note")
def add_comment(anomaly_id: int, body: CommentIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_anomalies"))):
    a = _get(db, anomaly_id, user)
    db.add(AnomalyEvent(anomaly_id=a.id, event_type="comment", comment=body.comment, actor=user.email or user.name))
    db.commit()
    return {"ok": True}
