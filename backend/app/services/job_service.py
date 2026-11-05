"""Background job queue on PostgreSQL (FOR UPDATE SKIP LOCKED).

Jobs are independent per subscription so a failure in one subscription never blocks the
others. Retries use exponential backoff; exhausted jobs raise an ingestion-failure alert.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import IngestionAuditLog, IngestionJob

ACTIVE_STATUSES = ("queued", "running")

JOB_TYPES = {
    "sync_subscription": "Discover and ingest new export runs for one subscription",
    "reprocess_subscription": "Re-ingest export runs for a subscription and date range",
    "backfill_cost_details": "Backfill history through the Cost Details API",
    "reattribute": "Re-apply allocation rules to stored billing records",
    "analytics": "Anomaly detection, savings, budget alerts and forecasts",
    "advisor_import": "Import Azure Advisor cost recommendations",
    "retention": "Drop raw billing partitions older than the retention setting",
}


def enqueue_job(
    db: Session,
    job_type: str,
    *,
    subscription_fk: int | None = None,
    dataset_type: str | None = None,
    params: dict[str, Any] | None = None,
    priority: int = 100,
    triggered_by: str = "system",
    dedupe: bool = True,
    parent_job_id: int | None = None,
) -> tuple[IngestionJob, bool]:
    """Queue a job. Returns (job, created). With ``dedupe`` an equivalent queued/running job
    is returned instead of creating a duplicate (avoids repeated Azure requests)."""
    if job_type not in JOB_TYPES:
        raise ValueError(f"Unknown job type {job_type}")
    params = params or {}
    if dedupe:
        existing = db.execute(
            select(IngestionJob)
            .where(
                IngestionJob.job_type == job_type,
                IngestionJob.status.in_(ACTIVE_STATUSES),
                IngestionJob.subscription_fk.is_(None) if subscription_fk is None else IngestionJob.subscription_fk == subscription_fk,
            )
            .order_by(IngestionJob.id)
        ).scalars().all()
        for job in existing:
            if (job.params or {}) == params and job.dataset_type == dataset_type:
                return job, False
    job = IngestionJob(
        job_type=job_type,
        status="queued",
        subscription_fk=subscription_fk,
        dataset_type=dataset_type,
        params=params,
        priority=priority,
        max_attempts=get_settings().job_max_attempts,
        triggered_by=triggered_by,
        parent_job_id=parent_job_id,
        progress={"pct": 0, "step": "queued"},
    )
    db.add(job)
    db.flush()
    return job, True


def claim_next_job(db: Session, worker_id: str) -> IngestionJob | None:
    row = db.execute(
        text(
            """
            UPDATE ingestion_jobs SET status = 'running', locked_by = :w, locked_at = now(),
                   started_at = now(), finished_at = NULL, attempts = attempts + 1
             WHERE id = (
                SELECT id FROM ingestion_jobs
                 WHERE status = 'queued' AND next_attempt_at <= now()
                 ORDER BY priority, id
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1)
            RETURNING id
            """
        ),
        {"w": worker_id},
    ).first()
    db.commit()
    if not row:
        return None
    return db.get(IngestionJob, row[0], populate_existing=True)  # never return a stale identity-map copy


def complete_job(db: Session, job: IngestionJob, result: dict[str, Any], status: str = "succeeded") -> None:
    job.status = status
    job.result = result
    job.finished_at = datetime.now(UTC)
    job.locked_by = None
    job.progress = {"pct": 100, "step": "done"}
    if status == "succeeded":
        job.error_message = None
        job.error_details = None


def fail_job(db: Session, job: IngestionJob, error: Exception | str, details: dict[str, Any] | None = None) -> bool:
    """Record a failure. Returns True when the job will be retried."""
    s = get_settings()
    job.error_message = str(error)[:4000]
    job.error_details = details
    job.locked_by = None
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=s.job_retry_backoff_seconds * (2 ** (job.attempts - 1)))
        job.progress = {"pct": 0, "step": f"retry scheduled (attempt {job.attempts + 1} of {job.max_attempts})"}
        return True
    job.status = "failed"
    job.finished_at = datetime.now(UTC)
    return False


def retry_job(db: Session, job: IngestionJob, actor: str) -> IngestionJob:
    job.status = "queued"
    job.attempts = 0
    job.next_attempt_at = datetime.now(UTC)
    job.error_message = None
    job.triggered_by = actor
    job.progress = {"pct": 0, "step": "queued (manual retry)"}
    return job


def requeue_stale_jobs(db: Session) -> int:
    minutes = get_settings().job_stale_after_minutes
    res = db.execute(
        text(
            "UPDATE ingestion_jobs SET status='queued', locked_by=NULL, next_attempt_at=now() "
            "WHERE status='running' AND locked_at < now() - make_interval(mins => :m)"
        ),
        {"m": minutes},
    )
    return res.rowcount or 0


def set_progress(session_factory, job_id: int, pct: float, step: str) -> None:
    """Progress is written in its own short transaction so it is visible immediately."""
    db = session_factory()
    try:
        db.execute(
            text("UPDATE ingestion_jobs SET progress = CAST(:p AS jsonb) WHERE id = :id"),
            {"p": json.dumps({"pct": round(pct, 1), "step": step}), "id": job_id},
        )
        db.commit()
    finally:
        db.close()


def audit(session_factory, *, operation: str, message: str, job_id: int | None = None, subscription_fk: int | None = None,
          level: str = "info", details: dict[str, Any] | None = None) -> None:
    db = session_factory()
    try:
        db.add(IngestionAuditLog(job_id=job_id, subscription_fk=subscription_fk, operation=operation, level=level, message=message, details=details))
        db.commit()
    finally:
        db.close()
