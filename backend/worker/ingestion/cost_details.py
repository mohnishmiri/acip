"""Supplementary historical backfill through the Cost Details API.

Admin-triggered only (never from a dashboard request) and de-duplicated by the job
queue so the same scope/date range is not regenerated repeatedly. The generated CSV
files are ingested through the same pipeline as exports.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import BinaryIO

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.azure_cost_management.client import ArmClient
from app.integrations.azure_storage.sources import BlobInfo
from app.models import AzureSubscription, ExportDefinition
from worker.ingestion.discovery import DiscoveredRun
from worker.ingestion.pipeline import IngestionFailure, process_run


class UrlSource:
    """Read files from time-limited SAS URLs returned by the Cost Details API."""

    kind = "url"

    def list_files(self, container: str, prefix: str) -> list[BlobInfo]:  # pragma: no cover - not used
        return []

    def download_to(self, container: str, path: str, fh: BinaryIO) -> None:
        with httpx.stream("GET", path, timeout=300) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes(1024 * 1024):
                fh.write(chunk)

    def read_bytes(self, container: str, path: str) -> bytes:  # pragma: no cover
        return httpx.get(path, timeout=300).content

    def check_access(self, container: str, prefix: str) -> tuple[bool, str]:  # pragma: no cover
        return True, "n/a"


def backfill(sf: sessionmaker[Session], subscription_fk: int, metric: str, start: date, end: date, job_id: int | None) -> dict:
    dataset = "actual" if metric == "ActualCost" else "amortized"
    with sf() as db:
        sub = db.get(AzureSubscription, subscription_fk)
        ed = db.execute(select(ExportDefinition).where(ExportDefinition.subscription_fk == subscription_fk, ExportDefinition.dataset_type == dataset)).scalars().first()
        if sub is None or ed is None:
            raise IngestionFailure(f"Subscription must have a '{dataset}' export definition to receive backfilled data")
        if sub.is_demo:
            raise IngestionFailure("Backfill is not available for demo subscriptions")
        db.expunge_all()
    urls = ArmClient().generate_cost_details(sub.subscription_id, metric, start, end)
    now = datetime.now(UTC)
    run = DiscoveredRun(
        run_key=f"cost-details/{metric}/{start:%Y%m%d}-{end:%Y%m%d}/{now:%Y%m%dT%H%M%S}",
        files=[BlobInfo(path=u, size=0, last_modified=now, etag=None) for u in urls],
        period_start=start,
        period_end=end,
        submitted_at=now,
    )
    outcome = process_run(sf, ed, sub, run, UrlSource(), job_id=job_id, force=True)
    if outcome.status == "failed":
        raise IngestionFailure(outcome.message or "Backfill failed", outcome.as_dict())
    return outcome.as_dict()
