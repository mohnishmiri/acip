from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.comparison import money
from app.core.db import get_db
from app.core.errors import NotFoundError, ValidationFailed
from app.models import AzureSubscription, ExportRun, IngestionAuditLog, IngestionError, IngestionFile, IngestionJob
from app.schemas.common import BackfillRequest, Envelope, IngestionTrigger, ReprocessRequest
from app.security.auth import CurrentUser, require
from app.services import audit_service, freshness_service, job_service
from app.services.labels import LabelResolver

router = APIRouter(prefix="/ingestion", tags=["Data Management & Ingestion"])


def job_out(j: IngestionJob, labels: LabelResolver) -> dict[str, Any]:
    sub = labels.subs.get(j.subscription_fk) if j.subscription_fk else None
    return {
        "id": j.id, "job_type": j.job_type, "status": j.status, "subscription_id": sub.subscription_id if sub else None,
        "subscription_name": sub.subscription_name if sub else None, "dataset_type": j.dataset_type, "params": j.params,
        "attempts": j.attempts, "max_attempts": j.max_attempts, "next_attempt_at": j.next_attempt_at.isoformat() if j.next_attempt_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None, "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "progress": j.progress, "result": j.result, "error_message": j.error_message, "triggered_by": j.triggered_by,
        "created_at": j.created_at.isoformat(), "parent_job_id": j.parent_job_id,
    }


@router.get("/status", summary="Freshness, coverage and active jobs per subscription")
def status(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    labels = LabelResolver(db)
    active = db.execute(select(IngestionJob).where(IngestionJob.status.in_(["queued", "running"])).order_by(IngestionJob.id)).scalars()
    return {"freshness": freshness_service.overall_freshness(db, user.allowed_subscription_fks), "active_jobs": [job_out(j, labels) for j in active]}


@router.get("/jobs", response_model=Envelope)
def jobs(
    status: list[str] = Query(default=[]),
    subscription: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require("read")),
):
    labels = LabelResolver(db)
    q = select(IngestionJob)
    if status:
        q = q.where(IngestionJob.status.in_(status))
    if subscription:
        s = labels.sub_by_guid.get(subscription.lower())
        q = q.where(IngestionJob.subscription_fk == (s.id if s else -1))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(IngestionJob.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [job_out(j, labels) for j in rows], "meta": {"total": total, "page": page, "page_size": page_size}}


@router.get("/jobs/{job_id}")
def job(job_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    j = db.get(IngestionJob, job_id)
    if j is None:
        raise NotFoundError("Job not found")
    labels = LabelResolver(db)
    errors = db.execute(select(IngestionError).where(IngestionError.job_id == job_id).order_by(IngestionError.id).limit(200)).scalars()
    logs = db.execute(select(IngestionAuditLog).where(IngestionAuditLog.job_id == job_id).order_by(IngestionAuditLog.id).limit(500)).scalars()
    return {
        **job_out(j, labels),
        "errors": [{"id": e.id, "error_type": e.error_type, "message": e.message, "row_number": e.row_number, "created_at": e.created_at.isoformat()} for e in errors],
        "logs": [{"operation": x.operation, "level": x.level, "message": x.message, "details": x.details, "created_at": x.created_at.isoformat()} for x in logs],
    }


@router.post("/trigger", summary="Queue synchronisation of Azure cost exports (one job per subscription)")
def trigger(body: IngestionTrigger, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    subs = list(db.execute(select(AzureSubscription).where(AzureSubscription.enabled.is_(True)).order_by(AzureSubscription.id)).scalars())
    if body.subscription_ids:
        wanted = {s.lower() for s in body.subscription_ids}
        subs = [s for s in subs if s.subscription_id in wanted]
        if not subs:
            raise ValidationFailed("None of the requested subscriptions are registered and enabled")
    params = {"force": body.force}
    if body.period_from:
        params["period_from"] = body.period_from.isoformat()
    if body.period_to:
        params["period_to"] = body.period_to.isoformat()
    if body.dataset_types:
        params["dataset_types"] = body.dataset_types
    out = []
    for s in subs:
        job, created = job_service.enqueue_job(db, "sync_subscription", subscription_fk=s.id, params=params, priority=50, triggered_by=user.email or user.name)
        out.append({"subscription_id": s.subscription_id, "job_id": job.id, "created": created})
    audit_service.record(db, user, "ingestion.trigger", details={"subscriptions": [o["subscription_id"] for o in out], **params}, request=request)
    db.commit()
    return {"jobs": out, "note": "Jobs already queued or running for a subscription are reused, not duplicated."}


@router.post("/retry/{job_id}")
def retry(job_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    j = db.get(IngestionJob, job_id)
    if j is None:
        raise NotFoundError("Job not found")
    if j.status not in ("failed", "cancelled", "partial"):
        raise ValidationFailed(f"Only failed jobs can be retried (status is {j.status})")
    job_service.retry_job(db, j, user.email or user.name)
    audit_service.record(db, user, "ingestion.retry", entity_type="ingestion_job", entity_id=str(job_id), request=request)
    db.commit()
    return {"job_id": j.id, "status": j.status}


@router.post("/reprocess", summary="Re-ingest export runs overlapping a date range (historical reprocessing)")
def reprocess(body: ReprocessRequest, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    s = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == body.subscription_id.lower())).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Subscription not registered")
    if body.period_to < body.period_from:
        raise ValidationFailed("period_to must not be before period_from")
    params = {"force": True, "period_from": body.period_from.isoformat(), "period_to": body.period_to.isoformat()}
    if body.dataset_types:
        params["dataset_types"] = body.dataset_types
    job, created = job_service.enqueue_job(db, "reprocess_subscription", subscription_fk=s.id, params=params, priority=60, triggered_by=user.email or user.name)
    audit_service.record(db, user, "ingestion.reprocess", entity_type="subscription", entity_id=s.subscription_id, details=params, request=request)
    db.commit()
    return {"job_id": job.id, "created": created}


@router.post("/backfill", summary="Backfill history via the Cost Details API (max one month per request)")
def backfill(body: BackfillRequest, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    s = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == body.subscription_id.lower())).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Subscription not registered")
    if (body.end_date - body.start_date).days > 31 or body.end_date < body.start_date:
        raise ValidationFailed("The Cost Details API accepts at most one month per request")
    params = {"metric": body.metric, "start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat()}
    job, created = job_service.enqueue_job(db, "backfill_cost_details", subscription_fk=s.id, params=params, priority=80, triggered_by=user.email or user.name)
    audit_service.record(db, user, "ingestion.backfill", entity_type="subscription", entity_id=s.subscription_id, details=params, request=request)
    db.commit()
    return {"job_id": job.id, "created": created}


@router.post("/analytics", summary="Re-run anomaly detection, savings evaluation and budget alerts")
def run_analytics(request: Request, lookback_days: int = Query(3, ge=1, le=120), db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    job, created = job_service.enqueue_job(db, "analytics", params={"lookback_days": lookback_days}, priority=70, triggered_by=user.email or user.name)
    audit_service.record(db, user, "analytics.trigger", details={"lookback_days": lookback_days}, request=request)
    db.commit()
    return {"job_id": job.id, "created": created}


@router.post("/advisor", summary="Import Azure Advisor cost recommendations (background job)")
def advisor_import(request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("ingestion"))):
    from app.core.config import get_settings

    if not get_settings().azure_enabled:
        raise ValidationFailed("Azure integration is disabled (AZURE_AUTH_MODE=disabled); Advisor recommendations cannot be imported.")
    job, created = job_service.enqueue_job(db, "advisor_import", params={}, priority=90, triggered_by=user.email or user.name)
    audit_service.record(db, user, "advisor.import", request=request)
    db.commit()
    return {"job_id": job.id, "created": created}


@router.get("/runs", response_model=Envelope, summary="Export run registry")
def runs(subscription: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
         db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    labels = LabelResolver(db)
    q = select(ExportRun)
    if subscription:
        s = labels.sub_by_guid.get(subscription.lower())
        q = q.where(ExportRun.subscription_fk == (s.id if s else -1))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(ExportRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [
        {"id": r.id, "subscription_name": labels.subscription(r.subscription_fk)[1], "dataset_type": r.dataset_type, "run_key": r.run_key,
         "period_start": r.period_start.isoformat() if r.period_start else None, "period_end": r.period_end.isoformat() if r.period_end else None,
         "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None, "status": r.status, "file_count": r.file_count,
         "row_count": r.row_count, "rows_rejected": r.rows_rejected, "total_cost": money(r.total_cost), "days_applied": r.days_applied,
         "days_skipped_newer": r.days_skipped_newer, "applied_at": r.applied_at.isoformat() if r.applied_at else None, "error": r.error}
        for r in rows
    ], "meta": {"total": total, "page": page, "page_size": page_size}}


@router.get("/files", response_model=Envelope, summary="Ingested source files (audit trail)")
def files(subscription: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
          db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    labels = LabelResolver(db)
    q = select(IngestionFile)
    if subscription:
        s = labels.sub_by_guid.get(subscription.lower())
        q = q.where(IngestionFile.subscription_fk == (s.id if s else -1))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(IngestionFile.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [
        {"id": f.id, "subscription_name": labels.subscription(f.subscription_fk)[1], "dataset_type": f.dataset_type, "blob_path": f.blob_path,
         "size_bytes": f.size_bytes, "content_hash": f.content_hash, "status": f.status, "rows_read": f.rows_read, "rows_loaded": f.rows_loaded,
         "rows_rejected": f.rows_rejected, "cost_total": money(f.cost_total), "detected_schema": f.detected_schema,
         "normalizer_version": f.normalizer_version, "processed_at": f.processed_at.isoformat() if f.processed_at else None, "error": f.error,
         "export_run_id": f.export_run_id}
        for f in rows
    ], "meta": {"total": total, "page": page, "page_size": page_size}}


@router.get("/errors", response_model=Envelope, summary="Data-quality / ingestion errors")
def errors(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    labels = LabelResolver(db)
    total = db.execute(select(func.count()).select_from(IngestionError)).scalar_one()
    rows = db.execute(select(IngestionError).order_by(IngestionError.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [
        {"id": e.id, "job_id": e.job_id, "export_run_id": e.export_run_id, "subscription_name": labels.subscription(e.subscription_fk)[1] if e.subscription_fk else None,
         "row_number": e.row_number, "error_type": e.error_type, "message": e.message, "created_at": e.created_at.isoformat()}
        for e in rows
    ], "meta": {"total": total, "page": page, "page_size": page_size}}


@router.get("/audit", response_model=Envelope, summary="Ingestion audit log")
def audit_log(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    labels = LabelResolver(db)
    total = db.execute(select(func.count()).select_from(IngestionAuditLog)).scalar_one()
    rows = db.execute(select(IngestionAuditLog).order_by(IngestionAuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [
        {"id": x.id, "job_id": x.job_id, "subscription_name": labels.subscription(x.subscription_fk)[1] if x.subscription_fk else None,
         "operation": x.operation, "level": x.level, "message": x.message, "details": x.details, "created_at": x.created_at.isoformat()}
        for x in rows
    ], "meta": {"total": total, "page": page, "page_size": page_size}}
