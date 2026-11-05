"""Job queue: claim, success, retry with backoff, permanent failure alerting."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import IngestionJob, NotificationHistory
from app.services import job_service

pytestmark = pytest.mark.integration


def test_job_lifecycle_success(demo_db, db):
    from worker.main import run_job

    job, created = job_service.enqueue_job(db, "analytics", params={"lookback_days": 1}, priority=1, triggered_by="test")
    db.commit()
    assert created
    dup, created2 = job_service.enqueue_job(db, "analytics", params={"lookback_days": 1}, triggered_by="test")
    assert not created2 and dup.id == job.id  # de-duplicated while queued
    claimed = job_service.claim_next_job(db, "test-worker")
    assert claimed.id == job.id and claimed.status == "running"
    db.expunge(claimed)
    run_job(claimed)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "succeeded" and j.result["anomalies"] is not None


def test_failed_job_retries_then_alerts(demo_db, db):
    from worker.main import run_job

    # backfill is refused for demo subscriptions -> a deterministic, real failure path
    params = {"metric": "ActualCost", "start_date": "2026-09-01", "end_date": "2026-09-30"}
    job, _ = job_service.enqueue_job(db, "backfill_cost_details", subscription_fk=demo_db["subscription_fks"][0], params=params, priority=1, triggered_by="test")
    job.max_attempts = 2
    db.commit()
    first = job_service.claim_next_job(db, "test-worker")
    db.expunge(first)
    run_job(first)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "queued" and j.attempts == 1 and "demo" in j.error_message
    assert j.next_attempt_at is not None
    # make it due now and fail again -> permanently failed + ingestion failure notification
    j.next_attempt_at = j.created_at
    db.commit()
    second = job_service.claim_next_job(db, "test-worker")
    assert second.id == job.id
    db.expunge(second)
    run_job(second)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "failed" and j.attempts == 2
    n = db.execute(select(NotificationHistory).where(NotificationHistory.dedup_key == f"ingestion_failed:{job.id}")).scalar_one()
    assert n.notification_type == "ingestion_failure"
    # manual retry resets attempts
    job_service.retry_job(db, j, "tester")
    db.commit()
    assert db.get(IngestionJob, job.id).status == "queued"
    db.get(IngestionJob, job.id).status = "cancelled"
    db.commit()
