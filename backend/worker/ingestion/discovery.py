"""Discover export runs under an export definition's blob prefix.

Supported layouts:

* Exports (v2, 2023+):  <root>/<export>/<YYYYMMDD-YYYYMMDD>/<runId>/part_*.csv[.gz] + manifest.json
* Legacy exports:       <root>/<export>/<YYYYMMDD-YYYYMMDD>/<export>_<guid>.csv   (one file = one run)
* Partitioned legacy:   <dir>/_manifest.json + part files

A *run* is the atomic unit of ingestion: all of its files are loaded together and replace
the run's reporting period for that subscription and dataset.
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.integrations.azure_storage.sources import BlobInfo, ExportSource
from worker.export_processing.normalizer import parse_iso_datetime

log = logging.getLogger(__name__)

PERIOD_RE = re.compile(r"(?<!\d)(\d{8})-(\d{8})(?!\d)")
DATA_SUFFIXES = (".csv", ".csv.gz", ".gz")
MANIFEST_NAMES = ("manifest.json", "_manifest.json")


@dataclass
class DiscoveredRun:
    run_key: str
    files: list[BlobInfo]
    manifest_path: str | None = None
    manifest: dict | None = None
    period_start: date | None = None
    period_end: date | None = None
    submitted_at: datetime | None = None
    expected_rows: dict[str, int] = field(default_factory=dict)  # blob path -> manifest row count
    warnings: list[str] = field(default_factory=list)


def _period_from_path(path: str) -> tuple[date | None, date | None]:
    m = PERIOD_RE.search(path)
    if not m:
        return None, None
    try:
        s = datetime.strptime(m.group(1), "%Y%m%d").date()
        e = datetime.strptime(m.group(2), "%Y%m%d").date()
        return s, e
    except ValueError:
        return None, None


def _is_data(path: str) -> bool:
    p = path.lower()
    return p.endswith(DATA_SUFFIXES) and not posixpath.basename(p).startswith("_")


def discover_runs(source: ExportSource, container: str, prefix: str) -> list[DiscoveredRun]:
    blobs = source.list_files(container, prefix)
    by_dir: dict[str, list[BlobInfo]] = {}
    for b in blobs:
        by_dir.setdefault(posixpath.dirname(b.path), []).append(b)

    runs: list[DiscoveredRun] = []
    for directory, items in sorted(by_dir.items()):
        manifest_blob = next((b for b in items if posixpath.basename(b.path).lower() in MANIFEST_NAMES), None)
        data = [b for b in items if _is_data(b.path)]
        unsupported = [b.path for b in items if b.path.lower().endswith(".parquet")]
        rel_dir = directory[len(prefix.rstrip("/")) :].strip("/") if directory.startswith(prefix.rstrip("/")) else directory
        if manifest_blob is not None:
            try:
                manifest = json.loads(source.read_bytes(container, manifest_blob.path))
            except Exception as exc:  # noqa: BLE001
                log.warning("Unreadable manifest", extra={"path": manifest_blob.path, "error": str(exc)})
                manifest = {}
            run_info = manifest.get("runInfo", {}) if isinstance(manifest, dict) else {}
            listed = manifest.get("blobs", []) if isinstance(manifest, dict) else []
            expected: dict[str, int] = {}
            if listed:
                names = {posixpath.basename(str(x.get("blobName", ""))): x for x in listed}
                chosen = [b for b in data if posixpath.basename(b.path) in names]
                for b in chosen:
                    rc = names[posixpath.basename(b.path)].get("dataRowCount")
                    if isinstance(rc, int):
                        expected[b.path] = rc
                missing = set(names) - {posixpath.basename(b.path) for b in chosen}
            else:
                chosen, missing = data, set()
            ps = pe = None
            if run_info.get("startDate"):
                sd = parse_iso_datetime(run_info.get("startDate"))
                ed = parse_iso_datetime(run_info.get("endDate"))
                ps, pe = (sd.date() if sd else None), (ed.date() if ed else None)
            if ps is None:
                ps, pe = _period_from_path(directory)
            submitted = parse_iso_datetime(run_info.get("submittedTime")) or max((b.last_modified for b in items if b.last_modified), default=None)
            run = DiscoveredRun(
                run_key=rel_dir or directory,
                files=chosen,
                manifest_path=manifest_blob.path,
                manifest=manifest if isinstance(manifest, dict) else None,
                period_start=ps,
                period_end=pe,
                submitted_at=submitted,
                expected_rows=expected,
            )
            if missing:
                run.warnings.append(f"{len(missing)} file(s) listed in the manifest are not present yet")
            if unsupported:
                run.warnings.append("Parquet files are not supported; configure the export to deliver CSV")
            runs.append(run)
        else:
            for b in data:
                ps, pe = _period_from_path(b.path)
                rel = b.path[len(prefix) :].lstrip("/") if b.path.startswith(prefix) else b.path
                runs.append(DiscoveredRun(run_key=rel, files=[b], period_start=ps, period_end=pe, submitted_at=b.last_modified))
    # Oldest period first, then by submission time so later revisions are applied last.
    runs.sort(key=lambda r: (r.period_start or date.min, r.submitted_at.timestamp() if r.submitted_at else 0.0, r.run_key))
    return runs
