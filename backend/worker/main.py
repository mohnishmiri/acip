"""Ingestion worker.

* Claims jobs from the PostgreSQL queue (FOR UPDATE SKIP LOCKED); any number of replicas
  can run concurrently.
* One replica (elected with a PostgreSQL advisory lock) schedules periodic work:
  export discovery per subscription and the analytics refresh. Azure exports run on
  Azure's schedule (UTC), so the worker polls for new runs instead of assuming a time.
* Writes a heartbeat file used by the Kubernetes liveness probe.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import get_engine, session_factory, use_batch_mode
from app.core.logging import configure_logging, log_context
from app.models import AzureSubscription
from app.services import job_service, notification_service
from app.services.email.delivery import deliver_pending
from worker.scheduled_jobs.handlers import HANDLERS

log = logging.getLogger("acip.worker")
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/acip-worker-heartbeat"))
LEADER_LOCK = 778899
_stop = False


def _on_signal(signum, _frame):
    global _stop
    log.info("Shutdown requested", extra={"signal": signum})
    _stop = True


def _beat() -> None:
    HEARTBEAT.write_text(datetime.now(UTC).isoformat())


class Scheduler:
    def __init__(self):
        self.settings = get_settings()
        self.leader_conn = None
        self.last_discovery = 0.0
        self.last_analytics = time.monotonic()
        self.last_stale_check = 0.0
        self.last_retention = time.monotonic()

    def is_leader(self) -> bool:
        try:
            if self.leader_conn is None:
                self.leader_conn = get_engine().connect()
            got = self.leader_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK}).scalar()
            self.leader_conn.commit()
            return bool(got)
        except Exception:  # noqa: BLE001
            log.exception("Leader election failed")
            self.leader_conn = None
            return False

    def tick(self) -> None:
        now = time.monotonic()
        sf = session_factory()
        if now - self.last_stale_check > 300:
            with sf() as db:
                n = job_service.requeue_stale_jobs(db)
                db.commit()
            if n:
                log.warning("Re-queued stale jobs", extra={"count": n})
            self.last_stale_check = now
        if not self.is_leader():
            return
        if now - self.last_discovery >= self.settings.export_discovery_interval_minutes * 60:
            with sf() as db:
                for s in db.execute(select(AzureSubscription).where(AzureSubscription.enabled.is_(True))).scalars():
                    job_service.enqueue_job(db, "sync_subscription", subscription_fk=s.id, params={"force": False}, priority=100, triggered_by="scheduler")
                db.commit()
            self.last_discovery = now
        if now - self.last_analytics >= self.settings.analytics_interval_minutes * 60:
            with sf() as db:
                job_service.enqueue_job(db, "analytics", params={}, priority=120, triggered_by="scheduler")
                if self.settings.azure_enabled:
                    job_service.enqueue_job(db, "advisor_import", params={}, priority=130, triggered_by="scheduler")
                db.commit()
            self.last_analytics = now
        if now - self.last_retention >= 24 * 3600:
            with sf() as db:
                job_service.enqueue_job(db, "retention", params={}, priority=200, triggered_by="scheduler")
                db.commit()
            self.last_retention = now


def run_job(job) -> None:
    sf = session_factory()
    handler = HANDLERS.get(job.job_type)
    with log_context(job_id=job.id, job_type=job.job_type, subscription_fk=job.subscription_fk):
        log.info("Job started", extra={"attempt": job.attempts})
        try:
            if handler is None:
                raise ValueError(f"No handler for job type {job.job_type}")
            result = handler(sf, job)
            with sf() as db:
                j = db.get(type(job), job.id)
                job_service.complete_job(db, j, result)
                db.commit()
            log.info("Job succeeded")
        except Exception as exc:  # noqa: BLE001
            details = getattr(exc, "details", None)
            log.exception("Job failed", extra={"error": str(exc)[:500]})
            with sf() as db:
                j = db.get(type(job), job.id)
                will_retry = job_service.fail_job(db, j, exc, details)
                if not will_retry:
                    sub = db.get(AzureSubscription, j.subscription_fk) if j.subscription_fk else None
                    notification_service.alert_for_ingestion_failure(db, j.id, sub.subscription_name if sub else None, str(exc))
                db.commit()


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_format)
    use_batch_mode()
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    log.info("Worker starting", extra={"worker_id": worker_id, "export_source": s.effective_export_source, "azure_auth_mode": s.azure_auth_mode})
    scheduler = Scheduler()
    sf = session_factory()
    while not _stop:
        _beat()
        try:
            scheduler.tick()
            sent = deliver_pending(sf)
            if any(sent.values()):
                log.info("Email deliveries processed", extra=sent)
            with sf() as db:
                job = job_service.claim_next_job(db, worker_id)
                if job is not None:
                    db.expunge(job)
            if job is not None:
                run_job(job)
                continue
        except Exception:  # noqa: BLE001 -- keep the worker alive
            log.exception("Worker loop error")
        for _ in range(s.worker_poll_interval_seconds * 2):
            if _stop:
                break
            time.sleep(0.5)
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
