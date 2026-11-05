"""Job handlers executed by the worker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.models import IngestionJob
from app.services import job_service
from worker.aggregation.reattribute import reattribute
from worker.anomaly_jobs.run import run_analytics_job
from worker.ingestion.pipeline import sync_subscription


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def handle_sync(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    p = job.params or {}
    result = sync_subscription(
        sf, job.subscription_fk, job_id=job.id, force=bool(p.get("force")), period_from=_d(p.get("period_from")),
        period_to=_d(p.get("period_to")), dataset_types=p.get("dataset_types"),
    )
    if result["runs_applied"]:
        with sf() as db:
            job_service.enqueue_job(db, "analytics", params={}, priority=70, triggered_by=f"job:{job.id}", parent_job_id=job.id)
            db.commit()
    return result


def handle_backfill(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    from worker.ingestion.cost_details import backfill

    p = job.params
    result = backfill(sf, job.subscription_fk, p["metric"], _d(p["start_date"]), _d(p["end_date"]), job.id)
    with sf() as db:
        job_service.enqueue_job(db, "analytics", params={}, priority=70, triggered_by=f"job:{job.id}", parent_job_id=job.id)
        db.commit()
    return result


def handle_reattribute(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    return reattribute(sf, job.subscription_fk)


def handle_analytics(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    return run_analytics_job(sf, (job.params or {}).get("lookback_days"))


def handle_advisor(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    from app.services.savings_service import import_advisor

    with sf() as db:
        out = import_advisor(db)
        db.commit()
    return out


def handle_retention(sf: sessionmaker[Session], job: IngestionJob) -> dict[str, Any]:
    from worker.aggregation.retention import apply_retention

    with sf() as db:
        out = apply_retention(db)
        db.commit()
    return out


HANDLERS: dict[str, Callable[[sessionmaker[Session], IngestionJob], dict[str, Any]]] = {
    "sync_subscription": handle_sync,
    "reprocess_subscription": handle_sync,
    "backfill_cost_details": handle_backfill,
    "reattribute": handle_reattribute,
    "analytics": handle_analytics,
    "advisor_import": handle_advisor,
    "retention": handle_retention,
}
