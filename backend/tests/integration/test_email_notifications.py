"""Email channel: queueing, sending, de-duplication, retries and the API."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import AlertRule, CostAnomaly, NotificationDelivery, NotificationHistory

pytestmark = pytest.mark.integration


class CaptureProvider:
    name = "capture"

    def __init__(self, fail_times: int = 0):
        self.sent = []
        self.fail_times = fail_times

    def send(self, msg):
        from app.services.email.providers import EmailSendError

        if self.fail_times:
            self.fail_times -= 1
            raise EmailSendError("simulated SMTP outage")
        self.sent.append(msg)
        return f"<msg-{len(self.sent)}@test>"


@pytest.fixture
def email_rule(db):
    rule = AlertRule(name="E2E email: anomalies", alert_type="anomaly", min_severity="informational", filters={}, params={},
                     channels=["in_app", "email"], email_recipients=["finops@example.com", "lead@example.com"], cooldown_hours=24, enabled=True)
    db.add(rule)
    db.commit()
    yield rule
    db.delete(rule)
    db.commit()


def _fresh_anomaly(db) -> CostAnomaly:
    taken = {n.entity_id for n in db.execute(select(NotificationHistory).where(NotificationHistory.notification_type == "anomaly")).scalars()}
    return next(a for a in db.execute(select(CostAnomaly).order_by(CostAnomaly.absolute_increase.desc())).scalars() if str(a.id) not in taken)


def test_anomaly_email_is_queued_sent_once_and_rendered_from_the_record(db, email_rule, monkeypatch):
    from app.core.db import session_factory
    from app.services import notification_service
    from app.services.email import delivery

    a = _fresh_anomaly(db)
    assert notification_service.alert_for_anomalies(db, [a.id]) >= 1
    db.commit()
    n = db.execute(select(NotificationHistory).where(NotificationHistory.dedup_key == f"anomaly:{a.id}")).scalar_one()
    d = db.execute(select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)).scalar_one()
    assert d.status == "pending" and d.recipients == ["finops@example.com", "lead@example.com"]

    cap = CaptureProvider()
    monkeypatch.setattr(delivery, "get_provider", lambda s=None: cap)
    stats = delivery.deliver_pending(session_factory())
    assert stats["sent"] >= 1
    db.expire_all()
    d = db.get(NotificationDelivery, d.id)
    assert d.status == "sent" and d.provider == "capture" and d.sent_at is not None
    msg = next(m for m in cap.sent if f"ANM-{a.id:06d}" in m.html)
    assert msg.to == ["finops@example.com", "lead@example.com"]
    assert msg.subject.startswith("[DEMO] [ACIP · ") and "severity]" in msg.subject
    assert "Investigate anomaly" in msg.html and f"/anomalies/{a.id}" in msg.html
    assert "Suggested investigation steps, not confirmed causes" in msg.html
    assert a.explanation[:40].replace("'", "&#39;") in msg.html or a.explanation[:40] in msg.html

    # the same unresolved anomaly never produces a second notification or email
    assert notification_service.alert_for_anomalies(db, [a.id]) == 0
    db.commit()
    assert db.execute(select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)).scalars().all() == [d]


def test_failed_delivery_retries_then_fails_and_disabled_is_skipped(db, monkeypatch):
    from datetime import UTC, datetime

    from app.core.config import get_settings
    from app.core.db import session_factory
    from app.services.email import delivery
    from app.services.email.providers import EmailNotConfigured
    from app.services.notification_service import notify

    assert notify(db, notification_type="data_delay", severity="medium", title="Retry test", message="m", dedup_key="test:email-retry", rule=None)
    n = db.execute(select(NotificationHistory).where(NotificationHistory.dedup_key == "test:email-retry")).scalar_one()
    d = delivery.queue_email(db, n.id, ["ops@example.com"])
    db.commit()
    cap = CaptureProvider(fail_times=99)
    monkeypatch.setattr(delivery, "get_provider", lambda s=None: cap)
    sf = session_factory()
    for _ in range(get_settings().email_max_attempts):
        db.execute(NotificationDelivery.__table__.update().where(NotificationDelivery.id == d.id).values(next_attempt_at=datetime.now(UTC)))
        db.commit()
        delivery.deliver_pending(sf)
    db.expire_all()
    d = db.get(NotificationDelivery, d.id)
    assert d.status == "failed" and d.attempts == get_settings().email_max_attempts and "simulated SMTP outage" in d.last_error

    n2_ok = notify(db, notification_type="data_delay", severity="medium", title="Disabled test", message="m", dedup_key="test:email-disabled", rule=None)
    assert n2_ok
    n2 = db.execute(select(NotificationHistory).where(NotificationHistory.dedup_key == "test:email-disabled")).scalar_one()
    d2 = delivery.queue_email(db, n2.id, ["ops@example.com"])
    db.commit()

    def disabled(s=None):
        raise EmailNotConfigured("Email delivery is disabled (EMAIL_PROVIDER=disabled).")

    monkeypatch.setattr(delivery, "get_provider", disabled)
    delivery.deliver_pending(sf)
    db.expire_all()
    d2 = db.get(NotificationDelivery, d2.id)
    assert d2.status == "skipped" and "disabled" in d2.last_error


def test_alert_rule_email_validation_and_endpoints(client, monkeypatch):
    base = {"name": "Email rule", "alert_type": "anomaly", "min_severity": "high", "filters": {}, "params": {}, "cooldown_hours": 24, "enabled": True}
    r = client.post("/api/v1/alert-rules", json={**base, "channels": ["in_app", "email"], "email_recipients": []})
    assert r.status_code == 422  # email channel needs recipients
    r = client.post("/api/v1/alert-rules", json={**base, "channels": ["email"], "email_recipients": ["not-an-email"]})
    assert r.status_code == 422
    r = client.post("/api/v1/alert-rules", json={**base, "channels": ["in_app", "email"], "email_recipients": ["FinOps@Example.com", "finops@example.com"]})
    assert r.status_code == 201
    rid = r.json()["id"]
    rule = next(x for x in client.get("/api/v1/alert-rules").json() if x["id"] == rid)
    assert rule["email_recipients"] == ["finops@example.com"]
    assert client.delete(f"/api/v1/alert-rules/{rid}").status_code == 204

    settings = client.get("/api/v1/notifications/email-settings").json()
    assert "provider" in settings and "smtp_password" not in str(settings).lower().replace("smtp_auth", "")

    nid = client.get("/api/v1/notifications").json()["data"][0]["id"]
    prev = client.get(f"/api/v1/notifications/{nid}/email-preview")
    assert prev.status_code == 200 and prev.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in prev.headers["content-security-policy"]
    assert client.get(f"/api/v1/notifications/{nid}/email-preview?format=text").text.startswith("Subject: ")

    from app.api.v1 import notifications as api

    cap = CaptureProvider()
    monkeypatch.setattr(api, "get_provider", lambda s=None: cap)
    r = client.post("/api/v1/notifications/test-email", json={"recipients": ["me@example.com"]})
    assert r.status_code == 200 and r.json()["sent"] is True and cap.sent[0].to == ["me@example.com"]
    viewer = client.post("/api/v1/notifications/test-email", json={"recipients": ["me@example.com"]}, headers={"X-ACIP-Dev-Role": "viewer"})
    assert viewer.status_code == 403


def test_anomaly_email_states_the_measured_window_not_the_episode_span(db):
    from datetime import timedelta

    from app.services.email.render import long_date, render_notification
    from app.services.notification_service import notify

    a = db.execute(select(CostAnomaly).where(CostAnomaly.evidence["observed_period"].isnot(None))).scalars().first()
    obs = a.evidence["observed_period"]
    original_end = a.period_end
    a.period_end = a.period_end + timedelta(days=3)  # episode extended by later re-detections
    db.flush()
    notify(db, notification_type="anomaly", severity=a.severity, title=a.title, message="m", dedup_key=f"test:window:{a.id}",
           entity_type="anomaly", entity_id=str(a.id), rule=None)
    n = db.execute(select(NotificationHistory).where(NotificationHistory.dedup_key == f"test:window:{a.id}")).scalar_one()
    r = render_notification(db, n)
    from datetime import date

    s, e = date.fromisoformat(obs["start"]), date.fromisoformat(obs["end"])
    expected = long_date(s) if s == e else f"{long_date(s)} – {long_date(e)}"
    assert f"Spend for {expected} was" in r.text
    assert long_date(a.period_end) not in r.text.split("DETAILS")[0]
    a.period_end = original_end
    db.rollback()
