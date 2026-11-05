"""Ingestion registry: jobs (also the work queue), export runs, files, errors, audit."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money


class IngestionJob(Base):
    """Unit of background work. The worker claims rows with FOR UPDATE SKIP LOCKED,
    so Postgres doubles as a durable queue and no Redis/Celery is required."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_queue", "status", "next_attempt_at", "priority"),
        Index("ix_ingestion_jobs_sub", "subscription_fk", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    subscription_fk: Mapped[int | None] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="SET NULL"))
    dataset_type: Mapped[str | None] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(200))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    triggered_by: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    parent_job_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExportRun(Base):
    __tablename__ = "export_runs"
    __table_args__ = (UniqueConstraint("export_definition_id", "run_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    export_definition_id: Mapped[int] = mapped_column(ForeignKey("export_definitions.id", ondelete="CASCADE"), nullable=False)
    subscription_fk: Mapped[int] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    run_key: Mapped[str] = mapped_column(String(700), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # discovered | processing | applied | partially_applied | superseded | skipped_duplicate | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count: Mapped[int | None] = mapped_column(Integer)
    rows_rejected: Mapped[int | None] = mapped_column(Integer)
    total_cost: Mapped[Decimal | None] = mapped_column(Money)
    days_applied: Mapped[int | None] = mapped_column(Integer)
    days_skipped_newer: Mapped[int | None] = mapped_column(Integer)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestionFile(Base):
    __tablename__ = "ingestion_files"
    __table_args__ = (
        UniqueConstraint("export_definition_id", "blob_path", "content_hash"),
        Index("ix_ingestion_files_hash", "export_definition_id", "content_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    export_run_id: Mapped[int | None] = mapped_column(ForeignKey("export_runs.id", ondelete="SET NULL"))
    export_definition_id: Mapped[int] = mapped_column(ForeignKey("export_definitions.id", ondelete="CASCADE"), nullable=False)
    subscription_fk: Mapped[int] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(200))
    last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # processing | processed | duplicate | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    rows_read: Mapped[int | None] = mapped_column(Integer)
    rows_loaded: Mapped[int | None] = mapped_column(Integer)
    rows_rejected: Mapped[int | None] = mapped_column(Integer)
    cost_total: Mapped[Decimal | None] = mapped_column(Money)
    detected_schema: Mapped[str | None] = mapped_column(String(64))
    source_columns: Mapped[list[Any] | None] = mapped_column(JSONB)
    schema_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    normalizer_version: Mapped[str | None] = mapped_column(String(32))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    __table_args__ = (Index("ix_ingestion_errors_job", "job_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    export_run_id: Mapped[int | None] = mapped_column(BigInteger)
    ingestion_file_id: Mapped[int | None] = mapped_column(BigInteger)
    subscription_fk: Mapped[int | None] = mapped_column(Integer)
    row_number: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestionAuditLog(Base):
    __tablename__ = "ingestion_audit_logs"
    __table_args__ = (Index("ix_ingestion_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    subscription_fk: Mapped[int | None] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
