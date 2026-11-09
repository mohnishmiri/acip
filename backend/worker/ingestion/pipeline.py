"""Idempotent export ingestion pipeline.

For each export run:
  1. register the run (export_runs) and download its files to a temp directory,
  2. hash file content (SHA-256); a run whose files were all processed before is skipped,
  3. stream-parse, validate and normalise rows; allocate application/environment/category,
  4. COPY rows into the UNLOGGED staging table,
  5. validate completeness (manifest row counts, rejection ratio),
  6. in ONE transaction: replace the run's reporting period for (subscription, dataset) --
     skipping days already supplied by a newer run -- rebuild aggregates and update the
     resource inventory.

Rows are never de-duplicated by hashing row content: legitimately identical billing rows
exist. Replace-by-slice semantics make re-processing the same or a revised (cumulative
month-to-date) export idempotent instead.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.allocation import AllocationEngine
from app.analytics.periods import add_months, month_start
from app.core.config import get_settings
from app.core.logging import log_context
from app.integrations.azure_storage.sources import ExportSource, get_export_source
from app.models import AzureSubscription, ExportDefinition, ExportRun, IngestionError, IngestionFile
from app.services.job_service import audit, set_progress
from worker.aggregation.rebuild import rebuild_aggregates
from worker.export_processing.normalizer import NORMALIZER_VERSION, RowError, RunContext, normalise_row
from worker.export_processing.schema import build_mapping
from worker.ingestion.discovery import DiscoveredRun, discover_runs

log = logging.getLogger(__name__)

STAGING_COLUMNS = [
    "usage_date", "dataset_type", "billing_currency", "subscription_fk", "application_id", "environment_id",
    "allocation_status", "service_category", "region", "charge_type", "pricing_model", "owner", "cost_center",
    "is_demo", "export_run_id", "ingestion_file_id", "source_row_number", "billing_period_start",
    "billing_period_end", "cost", "cost_usd", "payg_cost", "quantity", "unit_of_measure", "unit_price",
    "effective_price", "resource_id", "resource_key", "resource_name", "resource_group", "resource_type",
    "service_name", "service_family", "consumed_service", "meter_id", "meter_name", "meter_category",
    "meter_subcategory", "meter_region", "product_name", "sku", "frequency", "benefit_id", "benefit_name",
    "publisher_type", "source_cost_center", "tags", "additional_info", "extra", "project", "team",
    "business_unit", "workload", "attribution_source", "normalizer_version",
]
JSON_COLUMNS = {"tags", "additional_info", "extra"}
DATASET_LOCK_KEY = {"actual": 1, "amortized": 2, "focus": 3}
MAX_ERROR_SAMPLES = 200


class RunValidationError(Exception):
    pass


class IngestionFailure(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclass
class RunOutcome:
    run_key: str
    status: str
    rows_read: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    total_cost: Decimal = Decimal(0)
    days_applied: int = 0
    days_skipped_newer: int = 0
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_key": self.run_key,
            "status": self.status,
            "rows_read": self.rows_read,
            "rows_loaded": self.rows_loaded,
            "rows_rejected": self.rows_rejected,
            "total_cost": str(self.total_cost),
            "days_applied": self.days_applied,
            "days_skipped_newer": self.days_skipped_newer,
            "message": self.message,
        }


@dataclass
class _FileResult:
    file_id: int
    rows_read: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    cost_total: Decimal = Decimal(0)
    min_date: date | None = None
    max_date: date | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    mapping: Any = None


# ---------------------------------------------------------------------------------------
# partitions
# ---------------------------------------------------------------------------------------

def ensure_partitions(conn: Connection, start: date, end: date) -> None:
    m = month_start(start)
    while m <= end:
        name = f"cost_records_{m:%Y_%m}"
        exists = conn.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar()
        if not exists:
            conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
            nxt = add_months(m, 1)
            conn.execute(
                text(f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF cost_records FOR VALUES FROM ('{m.isoformat()}') TO ('{nxt.isoformat()}')")
            )
        m = add_months(m, 1)


# ---------------------------------------------------------------------------------------
# file parsing
# ---------------------------------------------------------------------------------------

def _open_text(path: str):
    with open(path, "rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig", newline="")
    return open(path, encoding="utf-8-sig", newline="")


def _copy_value(col: str, rec: dict[str, Any]) -> Any:
    v = rec.get(col)
    if col in JSON_COLUMNS:
        return json.dumps(v) if v else None
    return v


def load_file_to_staging(
    raw_conn,
    path: str,
    *,
    ctx: RunContext,
    engine: AllocationEngine,
    period: tuple[date, date] | None,
) -> _FileResult:
    res = _FileResult(file_id=ctx.ingestion_file_id)
    cols = ", ".join(STAGING_COLUMNS)
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        mapping = build_mapping(headers, ctx.dataset_type)
        res.mapping = mapping
        if mapping.missing_required:
            raise RunValidationError(f"Export file is missing required column(s): {', '.join(mapping.missing_required)} (detected schema: {mapping.detected_schema})")
        with raw_conn.cursor() as cur:
            with cur.copy(f"COPY cost_records_staging ({cols}) FROM STDIN") as cp:
                for row_number, raw in enumerate(reader, start=2):  # header is line 1
                    res.rows_read += 1
                    try:
                        rec = normalise_row(raw, mapping, ctx, row_number)
                        if period and not (period[0] <= rec["usage_date"] <= period[1]):
                            raise RowError("out_of_period", f"usage date {rec['usage_date']} outside run period {period[0]}..{period[1]}")
                    except RowError as exc:
                        res.rows_rejected += 1
                        if len(res.errors) < MAX_ERROR_SAMPLES:
                            res.errors.append({"row_number": row_number, "error_type": exc.error_type, "message": str(exc), "raw": {k: v for k, v in list(raw.items())[:40]}})
                        continue
                    alloc = engine.allocate(rec)
                    rec.update(
                        application_id=alloc.application_id,
                        environment_id=alloc.environment_id,
                        allocation_status=alloc.allocation_status,
                        service_category=alloc.service_category,
                        owner=alloc.owner,
                        cost_center=alloc.cost_center,
                        project=alloc.project,
                        team=alloc.team,
                        business_unit=alloc.business_unit,
                        workload=alloc.workload,
                        attribution_source=alloc.source,
                        source_cost_center=rec.pop("cost_center_column", None),
                    )
                    cp.write_row(tuple(_copy_value(c, rec) for c in STAGING_COLUMNS))
                    res.rows_loaded += 1
                    res.cost_total += rec["cost"]
                    d = rec["usage_date"]
                    res.min_date = d if res.min_date is None or d < res.min_date else res.min_date
                    res.max_date = d if res.max_date is None or d > res.max_date else res.max_date
    return res


# ---------------------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------------------

_RESOURCE_ATTRS = ["resource_id", "resource_name", "resource_type", "resource_group", "region", "sku", "service_category",
                   "tags", "application_id", "environment_id", "allocation_status", "owner", "cost_center"]


def apply_run(
    conn: Connection,
    *,
    run_id: int,
    subscription_fk: int,
    dataset_type: str,
    period_start: date,
    period_end: date,
    submitted_at: datetime,
    force: bool,
) -> tuple[int, int]:
    """Replace the run's period with staged rows. Returns (days_applied, days_skipped_newer)."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": subscription_fk, "b": DATASET_LOCK_KEY.get(dataset_type, 9)})
    ensure_partitions(conn, period_start, period_end)
    p = {"s": subscription_fk, "d": dataset_type, "a": period_start, "b": period_end, "r": run_id, "t": submitted_at}
    blocked: list[date] = []
    if not force:
        blocked = [
            r[0]
            for r in conn.execute(
                text("SELECT usage_date FROM cost_data_slices WHERE subscription_fk=:s AND dataset_type=:d AND usage_date BETWEEN :a AND :b AND run_submitted_at > :t"),
                p,
            )
        ]
    p["blocked"] = blocked
    conn.execute(
        text("DELETE FROM cost_records WHERE subscription_fk=:s AND dataset_type=:d AND usage_date BETWEEN :a AND :b AND NOT (usage_date = ANY(CAST(:blocked AS date[])))"),
        p,
    )
    cols = ", ".join(STAGING_COLUMNS)
    conn.execute(
        text(
            f"INSERT INTO cost_records ({cols}) SELECT {cols} FROM cost_records_staging "
            "WHERE export_run_id = :r AND usage_date BETWEEN :a AND :b AND NOT (usage_date = ANY(CAST(:blocked AS date[])))"
        ),
        p,
    )
    counts = dict(conn.execute(text("SELECT usage_date, COUNT(*) FROM cost_records_staging WHERE export_run_id=:r GROUP BY usage_date"), p).all())
    blocked_set = set(blocked)
    days = [period_start + timedelta(days=i) for i in range((period_end - period_start).days + 1)]
    applied_days = [d for d in days if d not in blocked_set]
    previous_runs = {
        r[0]
        for r in conn.execute(
            text("SELECT DISTINCT export_run_id FROM cost_data_slices WHERE subscription_fk=:s AND dataset_type=:d AND usage_date = ANY(CAST(:days AS date[])) AND export_run_id <> :r"),
            {**p, "days": applied_days},
        )
    }
    if applied_days:
        conn.execute(
            text(
                """INSERT INTO cost_data_slices (subscription_fk, dataset_type, usage_date, export_run_id, run_submitted_at, row_count, applied_at)
                   SELECT :s, :d, x.d, :r, :t, COALESCE(x.c, 0), now()
                     FROM unnest(CAST(:days AS date[]), CAST(:cnts AS int[])) AS x(d, c)
                   ON CONFLICT (subscription_fk, dataset_type, usage_date) DO UPDATE
                      SET export_run_id = EXCLUDED.export_run_id, run_submitted_at = EXCLUDED.run_submitted_at,
                          row_count = EXCLUDED.row_count, applied_at = now()"""
            ),
            {**p, "days": applied_days, "cnts": [int(counts.get(d, 0)) for d in applied_days]},
        )
        rebuild_aggregates(conn, subscription_fk, dataset_type, min(applied_days), max(applied_days))
    for old in previous_runs:
        # an earlier run whose days have all been replaced is now superseded (audit trail kept)
        still_used = conn.execute(text("SELECT 1 FROM cost_data_slices WHERE export_run_id = :o LIMIT 1"), {"o": old}).first()
        if not still_used:
            conn.execute(text("UPDATE export_runs SET status = 'superseded' WHERE id = :o AND status IN ('applied', 'partially_applied')"), {"o": old})

    upd = ", ".join(
        f"{c} = CASE WHEN EXCLUDED.last_seen_date >= COALESCE(azure_resources.last_seen_date, EXCLUDED.last_seen_date) THEN COALESCE(EXCLUDED.{c}, azure_resources.{c}) ELSE azure_resources.{c} END"
        for c in _RESOURCE_ATTRS
    )
    conn.execute(
        text(
            f"""INSERT INTO azure_resources (resource_key, {', '.join(_RESOURCE_ATTRS)}, subscription_fk, first_seen_date, last_seen_date, is_demo)
                SELECT DISTINCT ON (s.resource_key) s.resource_key, {', '.join('s.' + c for c in _RESOURCE_ATTRS)},
                       s.subscription_fk,
                       MIN(s.usage_date) OVER (PARTITION BY s.resource_key) AS first_seen,
                       MAX(s.usage_date) OVER (PARTITION BY s.resource_key) AS last_seen,
                       s.is_demo
                  FROM cost_records_staging s
                 WHERE s.export_run_id = :r AND s.resource_key <> ''
                 ORDER BY s.resource_key, s.usage_date DESC, s.cost DESC
                ON CONFLICT (resource_key) DO UPDATE SET {upd},
                   first_seen_date = LEAST(azure_resources.first_seen_date, EXCLUDED.first_seen_date),
                   last_seen_date = GREATEST(azure_resources.last_seen_date, EXCLUDED.last_seen_date)"""
        ),
        p,
    )
    conn.execute(
        text(
            """INSERT INTO resource_groups (subscription_fk, name, display_name, first_seen_date, last_seen_date)
               SELECT subscription_fk, resource_group, resource_group, MIN(usage_date), MAX(usage_date)
                 FROM cost_records_staging WHERE export_run_id = :r AND resource_group IS NOT NULL
                GROUP BY subscription_fk, resource_group
               ON CONFLICT (subscription_fk, name) DO UPDATE
                  SET first_seen_date = LEAST(resource_groups.first_seen_date, EXCLUDED.first_seen_date),
                      last_seen_date = GREATEST(resource_groups.last_seen_date, EXCLUDED.last_seen_date)"""
        ),
        p,
    )
    conn.execute(text("DELETE FROM cost_records_staging WHERE export_run_id = :r"), p)
    return len(applied_days), len(blocked)


# ---------------------------------------------------------------------------------------
# run processing
# ---------------------------------------------------------------------------------------

def _register_run(sf: sessionmaker[Session], export_def: ExportDefinition, run: DiscoveredRun, job_id: int | None, force: bool) -> tuple[int | None, str | None]:
    with sf() as db:
        er = db.execute(
            select(ExportRun).where(ExportRun.export_definition_id == export_def.id, ExportRun.run_key == run.run_key)
        ).scalar_one_or_none()
        if er and er.status in ("applied", "superseded", "skipped_duplicate", "skipped_empty") and not force:
            return None, er.status
        if er is None:
            er = ExportRun(
                export_definition_id=export_def.id,
                subscription_fk=export_def.subscription_fk,
                dataset_type=export_def.dataset_type,
                run_key=run.run_key,
            )
            db.add(er)
        er.status = "processing"
        er.job_id = job_id
        er.period_start = run.period_start
        er.period_end = run.period_end
        er.submitted_at = run.submitted_at or datetime.now(UTC)
        er.manifest = run.manifest
        er.file_count = len(run.files)
        er.error = None
        db.commit()
        return er.id, None


def _finish_run(sf, run_id: int, **fields) -> None:
    with sf() as db:
        er = db.get(ExportRun, run_id)
        if er:
            for k, v in fields.items():
                setattr(er, k, v)
            db.commit()


def process_run(
    sf: sessionmaker[Session],
    export_def: ExportDefinition,
    subscription: AzureSubscription,
    run: DiscoveredRun,
    source: ExportSource,
    *,
    job_id: int | None = None,
    force: bool = False,
) -> RunOutcome:
    settings = get_settings()
    run_id, prior = _register_run(sf, export_def, run, job_id, force)
    if run_id is None:
        return RunOutcome(run.run_key, f"already_{prior}")
    if any("not present yet" in w for w in run.warnings):
        _finish_run(sf, run_id, status="discovered", error="; ".join(run.warnings))
        return RunOutcome(run.run_key, "awaiting_files", message="; ".join(run.warnings))
    if not run.files:
        _finish_run(sf, run_id, status="failed", error="Run contains no CSV data files")
        return RunOutcome(run.run_key, "failed", message="Run contains no CSV data files")

    tmpdir = tempfile.mkdtemp(prefix="acip-run-")
    try:
        downloaded: list[tuple[Any, str, str, int]] = []
        for i, b in enumerate(run.files):
            local = os.path.join(tmpdir, f"{i:04d}.dat")
            # Parallel blob downloads need a seekable target, so hash after the file is complete.
            with open(local, "wb") as fh:
                source.download_to(export_def.container, b.path, fh)
            with open(local, "rb") as fh:
                digest = hashlib.file_digest(fh, "sha256").hexdigest()
            downloaded.append((b, local, digest, os.path.getsize(local)))

        with sf() as db:
            seen = {
                r[0]
                for r in db.execute(
                    select(IngestionFile.content_hash).where(
                        IngestionFile.export_definition_id == export_def.id,
                        IngestionFile.status == "processed",
                        IngestionFile.content_hash.in_([d[2] for d in downloaded]),
                    )
                )
            }
        if not force and all(d[2] in seen for d in downloaded):
            _finish_run(sf, run_id, status="skipped_duplicate", error=None)
            return RunOutcome(run.run_key, "skipped_duplicate", message="All files were already processed (identical content hash)")

        period = (run.period_start, run.period_end) if run.period_start and run.period_end else None
        db = sf()
        file_results: list[_FileResult] = []
        try:
            conn = db.connection()
            raw_conn = conn.connection.driver_connection
            engine = AllocationEngine.load(db)
            conn.execute(text("DELETE FROM cost_records_staging WHERE export_run_id = :r"), {"r": run_id})
            for b, local, digest, size in downloaded:
                f = db.execute(
                    select(IngestionFile).where(
                        IngestionFile.export_definition_id == export_def.id,
                        IngestionFile.blob_path == b.path,
                        IngestionFile.content_hash == digest,
                    )
                ).scalar_one_or_none()
                if f is None:
                    f = IngestionFile(export_definition_id=export_def.id, subscription_fk=export_def.subscription_fk,
                                      dataset_type=export_def.dataset_type, blob_path=b.path, content_hash=digest)
                    db.add(f)
                f.export_run_id = run_id
                f.size_bytes = size
                f.etag = b.etag
                f.last_modified = b.last_modified
                f.status = "processing"
                f.error = None
                db.flush()
                ctx = RunContext(
                    subscription_fk=subscription.id,
                    subscription_guid=subscription.subscription_id,
                    dataset_type=export_def.dataset_type,
                    default_currency=subscription.billing_currency,
                    export_run_id=run_id,
                    ingestion_file_id=f.id,
                    is_demo=subscription.is_demo,
                )
                fr = load_file_to_staging(raw_conn, local, ctx=ctx, engine=engine, period=period)
                file_results.append(fr)
                mapping = fr.mapping
                f.rows_read, f.rows_loaded, f.rows_rejected, f.cost_total = fr.rows_read, fr.rows_loaded, fr.rows_rejected, fr.cost_total
                f.detected_schema = mapping.detected_schema
                f.source_columns = mapping.source_columns
                f.schema_mapping = mapping.as_dict()
                f.normalizer_version = NORMALIZER_VERSION
                expected = run.expected_rows.get(b.path)
                if expected is not None and expected != fr.rows_read:
                    raise RunValidationError(f"Completeness check failed for {b.path}: manifest reports {expected} rows, file contains {fr.rows_read}")

            # The UNLOGGED staging table is bulk-loaded via COPY; refresh planner statistics so the
            # apply step does not plan against an "empty" table (that caused nested-loop rescans).
            conn.execute(text("ANALYZE cost_records_staging"))
            rows_read = sum(r.rows_read for r in file_results)
            rows_loaded = sum(r.rows_loaded for r in file_results)
            rows_rejected = sum(r.rows_rejected for r in file_results)
            total_cost = sum((r.cost_total for r in file_results), Decimal(0))
            if rows_read == 0:
                db.rollback()
                _finish_run(sf, run_id, status="skipped_empty", row_count=0, error="Export run contains no data rows; existing data left unchanged")
                return RunOutcome(run.run_key, "skipped_empty", message="No data rows")
            reject_pct = rows_rejected / rows_read * 100
            if reject_pct > settings.ingestion_reject_threshold_pct:
                samples = [e for r in file_results for e in r.errors][:5]
                raise RunValidationError(
                    f"{rows_rejected} of {rows_read} rows rejected ({reject_pct:.2f}% > {settings.ingestion_reject_threshold_pct}% threshold). "
                    f"First errors: {[s['message'] for s in samples]}"
                )
            if period is None:
                mins = [r.min_date for r in file_results if r.min_date]
                maxs = [r.max_date for r in file_results if r.max_date]
                period = (min(mins), max(maxs))
            days_applied, days_skipped = apply_run(
                conn,
                run_id=run_id,
                subscription_fk=subscription.id,
                dataset_type=export_def.dataset_type,
                period_start=period[0],
                period_end=period[1],
                submitted_at=run.submitted_at or datetime.now(UTC),
                force=force,
            )
            for fr in file_results:
                for e in fr.errors:
                    db.add(IngestionError(job_id=job_id, export_run_id=run_id, ingestion_file_id=fr.file_id, subscription_fk=subscription.id,
                                          row_number=e["row_number"], error_type=e["error_type"], message=e["message"], raw=e["raw"]))
            db.execute(
                text("UPDATE ingestion_files SET status='processed', processed_at=now() WHERE export_run_id=:r AND status='processing'"),
                {"r": run_id},
            )
            status = "applied" if days_skipped == 0 else ("superseded" if days_applied == 0 else "partially_applied")
            er = db.get(ExportRun, run_id)
            er.status = status
            er.row_count = rows_read
            er.rows_rejected = rows_rejected
            er.total_cost = total_cost
            er.days_applied = days_applied
            er.days_skipped_newer = days_skipped
            er.applied_at = datetime.now(UTC)
            er.period_start, er.period_end = period
            db.commit()
            return RunOutcome(run.run_key, status, rows_read, rows_loaded, rows_rejected, total_cost, days_applied, days_skipped)
        except Exception as exc:
            db.rollback()
            msg = str(exc)
            _finish_run(sf, run_id, status="failed", error=msg[:4000])
            with sf() as db2:
                db2.add(IngestionError(job_id=job_id, export_run_id=run_id, subscription_fk=subscription.id,
                                       error_type="run_failed" if isinstance(exc, RunValidationError) else "exception", message=msg[:4000]))
                for fr in file_results:
                    for e in fr.errors[:20]:
                        db2.add(IngestionError(job_id=job_id, export_run_id=run_id, subscription_fk=subscription.id,
                                               row_number=e["row_number"], error_type=e["error_type"], message=e["message"], raw=e["raw"]))
                db2.commit()
            log.exception("Export run failed", extra={"run_key": run.run_key})
            return RunOutcome(run.run_key, "failed", message=msg[:1000])
        finally:
            db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------------------
# subscription sync
# ---------------------------------------------------------------------------------------

def _overlaps(run: DiscoveredRun, start: date | None, end: date | None) -> bool:
    if start is None and end is None:
        return True
    if run.period_start is None or run.period_end is None:
        return True
    return not ((end and run.period_start > end) or (start and run.period_end < start))


def sync_subscription(
    sf: sessionmaker[Session],
    subscription_fk: int,
    *,
    job_id: int | None = None,
    force: bool = False,
    period_from: date | None = None,
    period_to: date | None = None,
    dataset_types: list[str] | None = None,
) -> dict[str, Any]:
    with sf() as db:
        sub = db.get(AzureSubscription, subscription_fk)
        if sub is None:
            raise IngestionFailure(f"Subscription {subscription_fk} not found")
        sub.last_sync_attempt_at = datetime.now(UTC)
        defs = [d for d in sub.export_definitions if d.enabled and (not dataset_types or d.dataset_type in dataset_types)]
        db.commit()
        db.expunge_all()

    outcomes: list[RunOutcome] = []
    def_errors: list[str] = []
    with log_context(subscription_id=sub.subscription_id, job_id=job_id):
        if not defs:
            audit(sf, operation="sync", message="No enabled export definitions configured", job_id=job_id, subscription_fk=subscription_fk, level="warning")
        for di, d in enumerate(defs):
            try:
                source = get_export_source(d.storage_account_url)
                runs = [r for r in discover_runs(source, d.container, d.blob_prefix) if _overlaps(r, period_from, period_to)]
                with sf() as db:
                    ed = db.get(ExportDefinition, d.id)
                    ed.last_discovery_at = datetime.now(UTC)
                    ed.last_discovery_error = None
                    db.commit()
            except Exception as exc:  # noqa: BLE001 -- isolate per export definition
                msg = f"{d.dataset_type} export '{d.export_name}': discovery failed: {exc}"
                def_errors.append(msg)
                with sf() as db:
                    ed = db.get(ExportDefinition, d.id)
                    ed.last_discovery_error = str(exc)[:2000]
                    db.commit()
                audit(sf, operation="discover", message=msg, job_id=job_id, subscription_fk=subscription_fk, level="error")
                continue
            for ri, run in enumerate(runs):
                if job_id:
                    pct = ((di + (ri / max(len(runs), 1))) / len(defs)) * 100
                    set_progress(sf, job_id, pct, f"{d.dataset_type}: {run.run_key}")
                outcome = process_run(sf, d, sub, run, source, job_id=job_id, force=force)
                outcomes.append(outcome)
                if outcome.status not in ("already_applied", "already_superseded", "already_skipped_duplicate", "already_skipped_empty"):
                    audit(sf, operation="process_run", message=f"{d.dataset_type} run {run.run_key}: {outcome.status}", job_id=job_id,
                          subscription_fk=subscription_fk, level="error" if outcome.status == "failed" else "info", details=outcome.as_dict())

    failed = [o for o in outcomes if o.status == "failed"]
    with sf() as db:
        s = db.get(AzureSubscription, subscription_fk)
        if failed or def_errors:
            s.last_sync_error = "; ".join(def_errors + [f"{o.run_key}: {o.message}" for o in failed])[:4000]
        else:
            s.last_successful_sync_at = datetime.now(UTC)
            s.last_sync_error = None
        db.commit()

    result = {
        "subscription_fk": subscription_fk,
        "runs_seen": len(outcomes),
        "runs_applied": sum(1 for o in outcomes if o.status in ("applied", "partially_applied")),
        "runs_failed": len(failed),
        "rows_loaded": sum(o.rows_loaded for o in outcomes),
        "definition_errors": def_errors,
        "outcomes": [o.as_dict() for o in outcomes if not o.status.startswith("already_")][:200],
    }
    if failed or def_errors:
        raise IngestionFailure(f"{len(failed)} run(s) failed, {len(def_errors)} export definition error(s)", result)
    return result
