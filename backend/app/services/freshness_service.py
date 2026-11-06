"""Data freshness: what data is available, how old it is, and whether ingestion is healthy.

Statuses never claim real-time data: the latest *usage date* and the last successful
ingestion are always shown separately.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AzureSubscription, DailyCostAggregate, IngestionJob
from app.services import settings_service

STATUS_ORDER = ["fresh", "demo", "processing", "awaiting_export", "partial", "delayed", "failed"]


def subscription_freshness(db: Session, allowed: set[int] | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    threshold = timedelta(hours=float(settings_service.get_setting(db, "freshness.delay_threshold_hours")))
    t = DailyCostAggregate.__table__
    latest: dict[tuple[int, str], Any] = {}
    earliest: dict[tuple[int, str], Any] = {}
    for sub_fk, ds, lo, hi in db.execute(select(t.c.subscription_fk, t.c.dataset_type, func.min(t.c.usage_date), func.max(t.c.usage_date)).group_by(t.c.subscription_fk, t.c.dataset_type)):
        latest[(sub_fk, ds)] = hi
        earliest[(sub_fk, ds)] = lo
    active_jobs = {
        r[0]
        for r in db.execute(select(IngestionJob.subscription_fk).where(IngestionJob.status.in_(["queued", "running"]), IngestionJob.subscription_fk.is_not(None)))
    }
    out = []
    for s in db.execute(select(AzureSubscription).order_by(AzureSubscription.id)).scalars():
        if allowed is not None and s.id not in allowed:
            continue
        la = latest.get((s.id, "actual"))
        lm = latest.get((s.id, "amortized"))
        if not s.enabled:
            status = "disabled"
        elif s.is_demo:
            status = "demo"
        elif s.id in active_jobs:
            status = "processing"
        elif la is None:
            status = "failed" if s.last_sync_error else "awaiting_export"
        elif s.last_sync_error and (s.last_successful_sync_at is None or (s.last_sync_attempt_at and s.last_sync_attempt_at > s.last_successful_sync_at)):
            status = "failed"
        elif now - datetime.combine(la + timedelta(days=1), time(0, 0), tzinfo=UTC) > threshold:
            status = "delayed"
        else:
            status = "fresh"
        out.append({
            "subscription_id": s.subscription_id,
            "subscription_name": s.subscription_name,
            "enabled": s.enabled,
            "is_demo": s.is_demo,
            "status": status,
            "latest_usage_date": {"actual": la.isoformat() if la else None, "amortized": lm.isoformat() if lm else None},
            "earliest_usage_date": {"actual": earliest.get((s.id, "actual")).isoformat() if earliest.get((s.id, "actual")) else None},
            "last_successful_sync_at": s.last_successful_sync_at.isoformat() if s.last_successful_sync_at else None,
            "last_sync_attempt_at": s.last_sync_attempt_at.isoformat() if s.last_sync_attempt_at else None,
            "last_sync_error": s.last_sync_error,
            "data_lag_hours": round((now - datetime.combine(la + timedelta(days=1), time(0, 0), tzinfo=UTC)).total_seconds() / 3600, 1) if la else None,
        })
    return out


def overall_freshness(db: Session, allowed: set[int] | None = None) -> dict[str, Any]:
    subs = [s for s in subscription_freshness(db, allowed) if s["enabled"]]
    statuses = {s["status"] for s in subs}
    if not subs:
        overall = "awaiting_export"
    elif statuses == {"demo"}:
        overall = "demo"
    elif "processing" in statuses:
        overall = "processing"
    elif statuses <= {"fresh", "demo"}:
        overall = "fresh"
    elif statuses == {"failed"}:
        overall = "failed"
    elif statuses == {"awaiting_export"}:
        overall = "awaiting_export"
    elif "fresh" in statuses or "demo" in statuses:
        overall = "partial"
    elif "failed" in statuses:
        overall = "failed"
    else:
        overall = "delayed"
    latest = max((s["latest_usage_date"]["actual"] for s in subs if s["latest_usage_date"]["actual"]), default=None)
    from datetime import date as _date

    complete = settings_service.complete_through(db, _date.fromisoformat(latest)) if latest else None
    oldest = min((s["latest_usage_date"]["actual"] for s in subs if s["latest_usage_date"]["actual"]), default=None)
    last_ok = max((s["last_successful_sync_at"] for s in subs if s["last_successful_sync_at"]), default=None)
    last_attempt = max((s["last_sync_attempt_at"] for s in subs if s["last_sync_attempt_at"]), default=None)
    with_data = sum(1 for s in subs if s["latest_usage_date"]["actual"])
    labels = {
        "fresh": "Fresh",
        "demo": "Demo data",
        "processing": "Processing",
        "awaiting_export": "Awaiting export",
        "partial": "Partial data",
        "delayed": "Delayed",
        "failed": "Failed",
    }
    return {
        "status": overall,
        "status_label": labels.get(overall, overall),
        "latest_usage_date": latest,
        # reports anchor here; later usage dates are partial (still being billed by Azure)
        "complete_through": complete.isoformat() if complete else None,
        "oldest_latest_usage_date": oldest,
        "last_successful_ingestion": last_ok,
        "last_ingestion_attempt": last_attempt,
        "subscriptions_with_data": with_data,
        "subscriptions_enabled": len(subs),
        "is_demo": any(s["is_demo"] for s in subs),
        "current_period_note": "Current-month charges are estimated and may be revised until the invoice is finalised.",
        "subscriptions": subs,
    }
