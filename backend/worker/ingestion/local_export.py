"""Local export mode: pull cost data with the Cost Details API into the local export folder.

Intended for evaluating real billing data before a storage account / Cost Management
exports are set up. For each subscription, month and dataset the Cost Details API
generates a CSV report (on Microsoft-managed storage, returned as SAS links); the files
are downloaded and written in the *same layout an Azure export writes to blob storage*:

    <LOCAL_EXPORT_ROOT>/<container>/<root_folder_path>/<export_name>/<YYYYMMDD-YYYYMMDD>/<runId>/part_0_000N.csv
                                                                                          manifest.json

The normal ingestion pipeline then picks them up (EXPORT_SOURCE=local). Each pull is a new
run with a newer submission time, so re-pulling a month replaces that month instead of
duplicating it. Switching to a storage account later only requires EXPORT_SOURCE=azure_blob
and AZURE_STORAGE_ACCOUNT_URL; folder names stay the same.

Read-only: nothing is created in the Azure subscriptions.
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.periods import add_months, month_end, month_start
from app.core.config import get_settings
from app.integrations.azure_cost_management.client import ArmClient
from app.models import AzureSubscription, ExportDefinition
from app.services.job_service import audit, set_progress

log = logging.getLogger(__name__)
METRIC = {"actual": "ActualCost", "amortized": "AmortizedCost"}
MAX_MONTHS = 13


class LocalExportError(Exception):
    pass


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-month pieces (the API accepts at most one month)."""
    if end < start:
        raise LocalExportError("end date is before start date")
    out = []
    m = month_start(start)
    while m <= end:
        out.append((max(m, start), min(month_end(m), end)))
        m = add_months(m, 1)
    return out


def default_range(months: int, today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(UTC).date()
    months = max(1, min(months, MAX_MONTHS))
    return month_start(add_months(month_start(today), -(months - 1))), today


def _definition(db: Session, subscription_fk: int, dataset: str) -> ExportDefinition | None:
    defs = list(
        db.execute(
            select(ExportDefinition).where(ExportDefinition.subscription_fk == subscription_fk, ExportDefinition.dataset_type == dataset, ExportDefinition.enabled.is_(True)).order_by(ExportDefinition.id)
        ).scalars()
    )
    # prefer the daily export when several exist for the same dataset (e.g. daily + last-month)
    return next((d for d in defs if "daily" in d.export_name), defs[0] if defs else None)


def _download(url: str, target: Path) -> int:
    """Stream one CSV to disk; returns the number of data rows."""
    with httpx.stream("GET", url, timeout=600, follow_redirects=True) as r:
        r.raise_for_status()
        with open(target, "wb") as fh:
            for chunk in r.iter_bytes(1024 * 1024):
                fh.write(chunk)
    with open(target, encoding="utf-8-sig", newline="") as fh:
        return max(sum(1 for _ in csv.reader(fh)) - 1, 0)


def pull_subscription(
    sf: sessionmaker[Session],
    subscription_fk: int,
    start: date,
    end: date,
    datasets: list[str],
    *,
    job_id: int | None = None,
    client: ArmClient | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    root = Path(settings.local_export_root)
    with sf() as db:
        sub = db.get(AzureSubscription, subscription_fk)
        if sub is None:
            raise LocalExportError(f"Subscription {subscription_fk} not found")
        if sub.is_demo:
            raise LocalExportError("Local export is not available for demo subscriptions")
        defs = {ds: _definition(db, subscription_fk, ds) for ds in datasets}
        db.expunge_all()
    missing = [ds for ds, d in defs.items() if d is None]
    if missing:
        raise LocalExportError(f"{sub.subscription_name}: no enabled export definition for dataset(s) {', '.join(missing)}")

    client = client or ArmClient()
    chunks = month_chunks(start, end)
    total = len(chunks) * len(datasets)
    done = 0
    runs: list[dict[str, Any]] = []
    for ds in datasets:
        d = defs[ds]
        for cs, ce in chunks:
            if job_id:
                set_progress(sf, job_id, done / total * 100, f"{sub.subscription_name}: {ds} {cs:%b %Y} — generating report")
            urls = client.generate_cost_details(sub.subscription_id, METRIC[ds], cs, ce)
            if not urls:
                runs.append({"dataset": ds, "month": f"{cs:%Y-%m}", "range": [cs.isoformat(), ce.isoformat()], "files": 0, "rows": 0, "folder": None,
                             "note": "Cost Details API reported no data for this range"})
                audit(sf, operation="local_export", message=f"{sub.subscription_name}: {ds} {cs:%Y-%m}: no data reported by Azure", job_id=job_id, subscription_fk=subscription_fk)
                done += 1
                continue
            # Replace window: from the requested start (never earlier, so days pulled before are kept)
            # to the end of that calendar month (later days do not exist yet for the current month).
            ms, me = cs, month_end(cs)
            submitted = datetime.now(UTC)
            run_id = str(uuid.uuid4())
            rel_dir = Path(d.root_folder_path.strip("/")) / d.export_name / f"{ms:%Y%m%d}-{me:%Y%m%d}" / run_id
            target = root / d.container / rel_dir
            target.mkdir(parents=True, exist_ok=True)
            blobs = []
            rows = 0
            for i, url in enumerate(urls, start=1):
                part = target / f"part_0_{i:04d}.csv"
                n = _download(url, part)
                rows += n
                blobs.append({"blobName": str(rel_dir / part.name), "byteCount": part.stat().st_size, "dataRowCount": n})
            manifest = {
                "manifestVersion": "2024-04-01",
                "byteCount": sum(b["byteCount"] for b in blobs),
                "blobCount": len(blobs),
                "dataRowCount": rows,
                "exportConfig": {
                    "exportName": d.export_name,
                    "resourceId": f"/subscriptions/{sub.subscription_id}",
                    "type": METRIC[ds],
                    "source": "CostDetailsAPI (local export mode)",
                    "requestedRange": {"start": cs.isoformat(), "end": ce.isoformat()},
                },
                "deliveryConfig": {"fileFormat": "Csv", "containerUri": f"local://{d.container}", "rootFolderPath": d.root_folder_path},
                # The period is the calendar month (like a month-to-date export), so the run replaces
                # the whole month for this subscription and dataset when ingested.
                "runInfo": {"executionType": "OnDemand", "submittedTime": submitted.isoformat().replace("+00:00", "Z"), "runId": run_id,
                            "startDate": f"{ms.isoformat()}T00:00:00", "endDate": f"{me.isoformat()}T00:00:00"},
                "blobs": blobs,
            }
            (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
            runs.append({"dataset": ds, "month": f"{ms:%Y-%m}", "range": [cs.isoformat(), ce.isoformat()], "files": len(blobs), "rows": rows, "folder": str(target)})
            audit(sf, operation="local_export", message=f"{sub.subscription_name}: {ds} {cs:%Y-%m}: {len(blobs)} file(s), {rows} row(s)", job_id=job_id,
                  subscription_fk=subscription_fk, details=runs[-1])
            log.info("Local export written", extra={"subscription": sub.subscription_name, **{k: v for k, v in runs[-1].items() if k != "folder"}})
            done += 1
    return {"subscription": sub.subscription_name, "range": [start.isoformat(), end.isoformat()], "runs": runs,
            "rows": sum(r["rows"] for r in runs), "files": sum(r["files"] for r in runs)}


def local_mode_enabled() -> bool:
    return get_settings().effective_export_source == "local"


def ensure_local_containers(db: Session) -> list[str]:
    """Create the local container folders so an empty local export area reads as 'no data yet', not 'failed'."""
    root = Path(get_settings().local_export_root)
    made = []
    for container in {d.container for d in db.execute(select(ExportDefinition)).scalars()}:
        p = root / container
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            made.append(str(p))
    return made


__all__ = ["LocalExportError", "default_range", "ensure_local_containers", "local_mode_enabled", "month_chunks", "pull_subscription"]
