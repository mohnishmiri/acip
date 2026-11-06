"""Notifications with de-duplication: in-app (always) and email (per alert rule).

Each notification has a ``dedup_key`` (e.g. ``anomaly:123``); the same unresolved issue never
produces a second notification -- and therefore never a second email. Email deliveries are
queued here and sent by the worker (``app.services.email.delivery``). Microsoft Teams remains
an extension point.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.anomaly_detection.rules import SEVERITY_RANK
from app.models import AlertRule, CostAnomaly, NotificationHistory, SavingsOpportunity
from app.services.labels import LabelResolver

log = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def deliver(self, notification: NotificationHistory) -> str: ...


class InAppChannel:
    name = "in_app"

    def deliver(self, notification: NotificationHistory) -> str:
        return "delivered"  # stored in notification_history; surfaced by the UI


class TeamsChannel:
    """Extension point: post an Adaptive Card to a Teams incoming webhook / Graph."""

    name = "teams"

    def deliver(self, notification: NotificationHistory) -> str:
        log.info("Teams channel not configured; notification kept in-app only", extra={"dedup_key": notification.dedup_key})
        return "not_configured"


CHANNELS: dict[str, NotificationChannel] = {c.name: c for c in (InAppChannel(), TeamsChannel())}


def notify(
    db: Session,
    *,
    notification_type: str,
    severity: str,
    title: str,
    message: str,
    dedup_key: str,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    rule: AlertRule | None = None,
    is_demo: bool = False,
) -> bool:
    stmt = (
        insert(NotificationHistory)
        .values(
            alert_rule_id=rule.id if rule else None,
            notification_type=notification_type,
            severity=severity,
            title=title[:400],
            message=message,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            dedup_key=dedup_key,
            channel="in_app",
            delivery_status="delivered",
            is_demo=is_demo,
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(NotificationHistory.id)
    )
    new_id = db.execute(stmt).scalar_one_or_none()
    if new_id is None:
        return False
    n = db.get(NotificationHistory, new_id)
    channels = (rule.channels if rule else ["in_app"]) or ["in_app"]
    for ch in channels:
        if ch == "email":
            from app.services.email.delivery import queue_email

            queue_email(db, n.id, list(rule.email_recipients or []) if rule else [])  # sent by the worker
        elif ch != "in_app" and ch in CHANNELS:
            n.delivery_status = CHANNELS[ch].deliver(n) if n.delivery_status == "delivered" else n.delivery_status
    return True


def _rules(db: Session, alert_type: str) -> list[AlertRule]:
    return list(db.execute(select(AlertRule).where(AlertRule.alert_type == alert_type, AlertRule.enabled.is_(True))).scalars())


def _matches(rule: AlertRule, labels: LabelResolver, *, severity: str | None = None, application_id: int | None = None,
             environment_id: int | None = None, service_category: str | None = None) -> bool:
    if rule.min_severity and severity and SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(rule.min_severity, 0):
        return False
    f = rule.filters or {}
    if f.get("application_ids") and application_id not in f["application_ids"]:
        return False
    if f.get("environment_groups"):
        env = labels.envs.get(environment_id) if environment_id is not None else None
        if env is None or env.environment_group not in f["environment_groups"]:
            return False
    if f.get("service_categories") and service_category not in f["service_categories"]:
        return False
    return True


def alert_for_anomalies(db: Session, anomaly_ids: list[int]) -> int:
    if not anomaly_ids:
        return 0
    labels = LabelResolver(db)
    rules = _rules(db, "anomaly")
    created = 0
    for a in db.execute(select(CostAnomaly).where(CostAnomaly.id.in_(anomaly_ids))).scalars():
        for rule in rules:
            if not _matches(rule, labels, severity=a.severity, application_id=a.application_id, environment_id=a.environment_id, service_category=a.service_category):
                continue
            pct = f" ({float(a.percentage_increase):+.1f}%)" if a.percentage_increase is not None else ""
            if notify(db, notification_type="anomaly", severity=a.severity, title=a.title,
                      message=f"Increase of {a.billing_currency} {float(a.absolute_increase):,.2f}{pct} detected on {a.detection_date.isoformat()}.",
                      dedup_key=f"anomaly:{a.id}", link=f"/anomalies/{a.id}", entity_type="anomaly", entity_id=str(a.id), rule=rule, is_demo=a.is_demo):
                created += 1
            break
    return created


def alert_for_budgets(db: Session, statuses: list[dict[str, Any]]) -> int:
    created = 0
    thr_rules = _rules(db, "budget_threshold")
    fc_rules = _rules(db, "budget_forecast")
    for b in statuses:
        if not b["enabled"]:
            continue
        for t in b["thresholds_crossed"]:
            for rule in thr_rules[:1]:
                sev = "high" if float(t) >= 100 else "medium" if float(t) >= 90 else "low"
                if notify(db, notification_type="budget_threshold", severity=sev,
                          title=f"Budget '{b['name']}' reached {float(t):.0f}%",
                          message=f"{b['scope_label']}: {b['currency']} {b['actual']:,.2f} of {b['amount']:,.2f} used ({b['utilization_pct']:.1f}%) for {b['period_start']} – {b['period_end']}.",
                          dedup_key=f"budget:{b['id']}:{b['period_start']}:{float(t):g}", link="/budgets", entity_type="budget", entity_id=str(b["id"]),
                          rule=rule, is_demo=b["is_demo"]):
                    created += 1
        if b["forecast_alert"] and b["forecast_exceeds_budget"]:
            for rule in fc_rules[:1]:
                if notify(db, notification_type="budget_forecast", severity="medium",
                          title=f"Forecast exceeds budget '{b['name']}'",
                          message=f"{b['scope_label']}: forecast {b['currency']} {b['forecast']:,.2f} vs budget {b['amount']:,.2f} ({b['forecast_method_label']}). Forecasts are projections, not actual charges.",
                          dedup_key=f"budget_forecast:{b['id']}:{b['period_start']}", link="/budgets", entity_type="budget", entity_id=str(b["id"]),
                          rule=rule, is_demo=b["is_demo"]):
                    created += 1
    return created


def alert_for_data_delay(db: Session, freshness: list[dict[str, Any]]) -> int:
    created = 0
    for rule in _rules(db, "data_delay")[:1]:
        for s in freshness:
            if s["status"] in ("delayed", "failed") and not s["is_demo"]:
                latest = s["latest_usage_date"]["actual"] or "none"
                if notify(db, notification_type="data_delay", severity="medium",
                          title=f"Cost data {'delayed' if s['status'] == 'delayed' else 'failing'} for {s['subscription_name']}",
                          message=f"Latest usage date: {latest}. Last successful ingestion: {s['last_successful_sync_at'] or 'never'}. {s['last_sync_error'] or ''}".strip(),
                          dedup_key=f"data_delay:{s['subscription_id']}:{latest}:{s['status']}", link="/data-management", entity_type="subscription",
                          entity_id=s["subscription_id"], rule=rule):
                    created += 1
    return created


def alert_for_ingestion_failure(db: Session, job_id: int, subscription_name: str | None, error: str) -> bool:
    for rule in _rules(db, "ingestion_failure")[:1]:
        return notify(db, notification_type="ingestion_failure", severity="high",
                      title=f"Ingestion failed{' for ' + subscription_name if subscription_name else ''}",
                      message=error[:1000], dedup_key=f"ingestion_failed:{job_id}", link="/data-management",
                      entity_type="ingestion_job", entity_id=str(job_id), rule=rule)
    return False


def alert_for_savings(db: Session, opportunity_ids: list[int]) -> int:
    created = 0
    for rule in _rules(db, "savings_opportunity")[:1]:
        min_sav = float((rule.params or {}).get("min_monthly_savings", 0))
        for o in db.execute(select(SavingsOpportunity).where(SavingsOpportunity.id.in_(opportunity_ids or [-1]))).scalars():
            if o.estimated_monthly_savings is None or float(o.estimated_monthly_savings) < min_sav:
                continue
            if notify(db, notification_type="savings_opportunity", severity="informational", title=f"Potential savings: {o.title}",
                      message=f"Estimated {o.billing_currency} {float(o.estimated_monthly_savings):,.2f}/month (estimate, not realised). Source: {o.evidence_source}.",
                      dedup_key=f"savings:{o.id}", link="/savings", entity_type="savings_opportunity", entity_id=str(o.id), rule=rule, is_demo=o.is_demo):
                created += 1
    return created


def mark_read(db: Session, ids: list[int] | None, actor: str) -> int:
    q = select(NotificationHistory).where(NotificationHistory.is_read.is_(False))
    if ids:
        q = q.where(NotificationHistory.id.in_(ids))
    n = 0
    for row in db.execute(q).scalars():
        row.is_read = True
        row.read_at = datetime.now(UTC)
        row.read_by = actor
        n += 1
    return n

