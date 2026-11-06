"""Queued email delivery with retries (runs in the worker loop).

``notify`` only records a pending delivery; the worker renders and sends it, so mail-server
latency or outages never slow down anomaly detection or API requests. Each notification is
emailed at most once per channel (unique constraint), which keeps the "one alert per
unresolved issue" guarantee for email as well.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import NotificationDelivery, NotificationHistory
from app.services.email.providers import EmailNotConfigured, EmailSendError, OutgoingEmail, get_provider
from app.services.email.render import render_notification

log = logging.getLogger(__name__)


def deliver_pending(sf: sessionmaker[Session], limit: int = 25) -> dict[str, int]:
    stats = {"sent": 0, "failed": 0, "retry": 0, "skipped": 0}
    for _ in range(limit):
        with sf() as db:
            row = db.execute(
                text("SELECT id FROM notification_deliveries WHERE status = 'pending' AND next_attempt_at <= now() "
                     "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1")
            ).first()
            if row is None:
                break
            d = db.get(NotificationDelivery, row[0])
            outcome = _send_one(db, d)
            stats[outcome] += 1
            db.commit()
    return stats


def _send_one(db: Session, d: NotificationDelivery) -> str:
    s = get_settings()
    n = db.get(NotificationHistory, d.notification_id)
    d.attempts += 1
    if not d.recipients:
        d.status, d.last_error = "skipped", "No email recipients configured on the alert rule."
        return "skipped"
    try:
        provider = get_provider(s)
    except EmailNotConfigured as exc:
        d.status, d.last_error = "skipped", str(exc)
        return "skipped"
    try:
        rendered = render_notification(db, n)
        d.subject = rendered.subject[:400]
        msg_id = provider.send(OutgoingEmail(
            to=list(d.recipients), subject=rendered.subject, html=rendered.html, text=rendered.text,
            headers={"X-ACIP-Notification": str(n.id), "X-ACIP-Type": n.notification_type},
        ))
    except (EmailSendError, EmailNotConfigured, Exception) as exc:  # noqa: BLE001 -- record and retry
        d.last_error = str(exc)[:2000]
        if d.attempts >= s.email_max_attempts:
            d.status = "failed"
            log.error("Email delivery failed permanently", extra={"delivery_id": d.id, "error": d.last_error})
            return "failed"
        d.next_attempt_at = datetime.now(UTC) + timedelta(minutes=2 ** d.attempts)
        log.warning("Email delivery failed; will retry", extra={"delivery_id": d.id, "attempt": d.attempts, "error": d.last_error})
        return "retry"
    d.status, d.provider, d.provider_message_id, d.sent_at, d.last_error = "sent", provider.name, msg_id[:300], datetime.now(UTC), None
    log.info("Email sent", extra={"delivery_id": d.id, "notification_id": n.id, "recipients": len(d.recipients)})
    return "sent"


def queue_email(db: Session, notification_id: int, recipients: list[str]) -> NotificationDelivery:
    d = NotificationDelivery(notification_id=notification_id, channel="email", recipients=sorted({r.strip().lower() for r in recipients if r.strip()}),
                             status="pending", attempts=0)
    db.add(d)
    return d


def deliveries_by_notification(db: Session, ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    if not ids:
        return out
    for d in db.query(NotificationDelivery).filter(NotificationDelivery.notification_id.in_(ids)).all():
        out.setdefault(d.notification_id, []).append({
            "id": d.id, "channel": d.channel, "status": d.status, "recipients": d.recipients, "attempts": d.attempts,
            "last_error": d.last_error, "sent_at": d.sent_at.isoformat() if d.sent_at else None, "subject": d.subject,
        })
    return out
