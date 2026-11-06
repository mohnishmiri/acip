from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ExternalServiceError, NotFoundError, ValidationFailed
from app.models import AlertRule, NotificationDelivery, NotificationHistory
from app.schemas.common import AlertRuleIn, Envelope, MarkRead, TestEmailIn
from app.security.auth import CurrentUser, require
from app.services import audit_service, notification_service
from app.services.email.delivery import deliveries_by_notification
from app.services.email.providers import EmailNotConfigured, EmailSendError, OutgoingEmail, get_provider
from app.services.email.providers import describe as describe_email
from app.services.email.render import render_notification, render_test

router = APIRouter(tags=["Alerts & Notifications"])


@router.get("/notifications", response_model=Envelope)
def list_notifications(
    unread_only: bool = False,
    notification_type: list[str] = Query(default=[]),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    q = select(NotificationHistory)
    if unread_only:
        q = q.where(NotificationHistory.is_read.is_(False))
    if notification_type:
        q = q.where(NotificationHistory.notification_type.in_(notification_type))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    unread = db.execute(select(func.count()).select_from(NotificationHistory).where(NotificationHistory.is_read.is_(False))).scalar_one()
    rows = list(db.execute(q.order_by(NotificationHistory.created_at.desc(), NotificationHistory.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars())
    deliveries = deliveries_by_notification(db, [n.id for n in rows])
    return {
        "data": [
            {"id": n.id, "type": n.notification_type, "severity": n.severity, "title": n.title, "message": n.message, "link": n.link,
             "entity_type": n.entity_type, "entity_id": n.entity_id, "is_read": n.is_read, "created_at": n.created_at.isoformat(),
             "delivery_status": n.delivery_status, "is_demo": n.is_demo, "deliveries": deliveries.get(n.id, [])}
            for n in rows
        ],
        "meta": {"total": total, "unread": unread, "page": page, "page_size": page_size},
    }


@router.get("/notifications/email-settings", summary="Email delivery configuration (no secrets) and delivery statistics")
def email_settings(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    counts = dict(db.execute(select(NotificationDelivery.status, func.count()).where(NotificationDelivery.channel == "email").group_by(NotificationDelivery.status)).all())
    return {**describe_email(), "deliveries": counts}


@router.post("/notifications/test-email", summary="Send a test email now (verifies the configured provider)")
def test_email(body: TestEmailIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_alerts"))):
    rendered = render_test(body.recipients)
    try:
        msg_id = get_provider().send(OutgoingEmail(to=body.recipients, subject=rendered.subject, html=rendered.html, text=rendered.text,
                                                   headers={"X-ACIP-Type": "test"}))
    except EmailNotConfigured as exc:
        raise ValidationFailed(str(exc)) from exc
    except EmailSendError as exc:
        raise ExternalServiceError(f"The email could not be sent: {exc}") from exc
    audit_service.record(db, user, "notifications.test_email", details={"recipients": body.recipients}, request=request)
    db.commit()
    return {"sent": True, "recipients": body.recipients, "subject": rendered.subject, "message_id": msg_id}


@router.get("/notifications/{notification_id}/email-preview", summary="Rendered email for a notification (HTML, or text with format=text)")
def email_preview(notification_id: int, format: str = Query("html", pattern="^(html|text)$"), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    n = db.get(NotificationHistory, notification_id)
    if n is None:
        raise NotFoundError("Notification not found")
    rendered = render_notification(db, n)
    if format == "text":
        return PlainTextResponse(f"Subject: {rendered.subject}\n\n{rendered.text}")
    # Rendered inside a sandboxed iframe by the UI; all record values are HTML-escaped by the template.
    return HTMLResponse(rendered.html, headers={"X-Email-Subject": rendered.subject.encode("ascii", "replace").decode(), "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:"})


@router.post("/notifications/read", summary="Mark notifications as read (all when ids omitted)")
def mark_read(body: MarkRead, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    n = notification_service.mark_read(db, body.ids, user.email or user.name)
    db.commit()
    return {"updated": n}


@router.get("/alert-rules")
def list_alert_rules(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [
        {"id": r.id, "name": r.name, "alert_type": r.alert_type, "min_severity": r.min_severity, "filters": r.filters, "params": r.params,
         "channels": r.channels, "email_recipients": r.email_recipients or [], "cooldown_hours": r.cooldown_hours, "enabled": r.enabled}
        for r in db.execute(select(AlertRule).order_by(AlertRule.id)).scalars()
    ]


@router.post("/alert-rules", status_code=201)
def create_alert_rule(body: AlertRuleIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_alerts"))):
    r = AlertRule(**body.model_dump())
    db.add(r)
    db.flush()
    audit_service.record(db, user, "alert_rule.create", entity_type="alert_rule", entity_id=str(r.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": r.id}


@router.put("/alert-rules/{rule_id}")
def update_alert_rule(rule_id: int, body: AlertRuleIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_alerts"))):
    r = db.get(AlertRule, rule_id)
    if r is None:
        raise NotFoundError("Alert rule not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit_service.record(db, user, "alert_rule.update", entity_type="alert_rule", entity_id=str(r.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": r.id}


@router.delete("/alert-rules/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("manage_alerts"))):
    r = db.get(AlertRule, rule_id)
    if r is None:
        raise NotFoundError("Alert rule not found")
    db.delete(r)
    audit_service.record(db, user, "alert_rule.delete", entity_type="alert_rule", entity_id=str(rule_id), request=request)
    db.commit()
