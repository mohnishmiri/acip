"""Idempotency, revisions, ordering, completeness validation and failure isolation."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.models import AzureSubscription, CostRecord, ExportRun

pytestmark = pytest.mark.integration

SEPT = ("20260901-20260930", "2026-09-01", "2026-09-30")


def _sub(db, idx: int) -> AzureSubscription:
    from app.demo.catalog import SUBSCRIPTIONS

    return db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == SUBSCRIPTIONS[idx - 1][3])).scalar_one()


def _totals(db, sub_id: int, start: str, end: str) -> tuple[int, Decimal]:
    row = db.execute(
        text("SELECT COUNT(*), COALESCE(SUM(cost),0) FROM cost_records WHERE subscription_fk=:s AND dataset_type='actual' AND usage_date BETWEEN :a AND :b"),
        {"s": sub_id, "a": start, "b": end},
    ).one()
    agg = db.execute(
        text("SELECT COALESCE(SUM(cost),0) FROM daily_cost_aggregates WHERE subscription_fk=:s AND dataset_type='actual' AND usage_date BETWEEN :a AND :b"),
        {"s": sub_id, "a": start, "b": end},
    ).scalar_one()
    assert Decimal(agg) == Decimal(row[1])  # aggregates always consistent with raw records
    return row[0], Decimal(row[1])


def _final_run_dir(root: Path, guid: str, period: str) -> Path:
    base = root / "cost-exports" / "demo" / guid / "actual" / "acip-actual-daily" / period
    runs = sorted(base.iterdir(), key=lambda p: json.loads((p / "manifest.json").read_text())["runInfo"]["submittedTime"])
    return runs[-1]


def _write_run(src: Path, submitted: str, transform=None, extra_newline=False, header_override=None) -> Path:
    dst = src.parent / str(uuid.uuid4())
    dst.mkdir()
    rows = list(csv.DictReader(open(src / "part_0_0001.csv", newline="")))
    headers = header_override or list(rows[0].keys())
    if transform:
        rows = [transform(dict(r)) for r in rows]
    with open(dst / "part_0_0001.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        if extra_newline:
            fh.write("\n")
    m = json.loads((src / "manifest.json").read_text())
    m["runInfo"]["submittedTime"] = submitted
    m["runInfo"]["runId"] = dst.name
    rel = str((dst / "part_0_0001.csv").relative_to(src.parents[6] / "cost-exports"))
    m["blobs"] = [{"blobName": rel, "dataRowCount": len(rows)}]
    m["dataRowCount"] = len(rows)
    (dst / "manifest.json").write_text(json.dumps(m))
    return dst


def test_reprocessing_same_files_creates_no_duplicates(demo_db, db):
    from worker.ingestion.pipeline import sync_subscription

    sub = _sub(db, 6)
    before = _totals(db, sub.id, "2025-01-01", "2026-11-01")
    res = sync_subscription(demo_db["session_factory"], sub.id)
    assert res["runs_applied"] == 0  # everything already applied
    forced = sync_subscription(demo_db["session_factory"], sub.id, force=True)
    assert forced["runs_applied"] > 0
    db.expire_all()
    assert _totals(db, sub.id, "2025-01-01", "2026-11-01") == before


def test_revised_export_replaces_instead_of_appending(demo_db, db):
    from worker.ingestion.pipeline import sync_subscription

    sub = _sub(db, 6)
    root = demo_db["root"]
    count0, total0 = _totals(db, sub.id, SEPT[1], SEPT[2])
    sep5 = db.execute(text("SELECT SUM(cost) FROM cost_records WHERE subscription_fk=:s AND dataset_type='actual' AND usage_date='2026-09-05'"), {"s": sub.id}).scalar_one()
    src = _final_run_dir(root, sub.subscription_id, SEPT[0])

    def double_sep5(r):
        if r["date"] == "09/05/2026":
            r["costInBillingCurrency"] = f"{Decimal(r['costInBillingCurrency']) * 2:.2f}"
        return r

    revised = _write_run(src, "2026-10-20T06:00:00Z", double_sep5)
    sync_subscription(demo_db["session_factory"], sub.id)
    db.expire_all()
    count1, total1 = _totals(db, sub.id, SEPT[1], SEPT[2])
    assert count1 == count0  # replaced, not appended
    assert total1 == total0 + Decimal(sep5)
    # the run it replaced is now marked superseded (audit trail kept)
    statuses = {r.run_key.split("/")[-1]: r.status for r in db.execute(select(ExportRun).where(ExportRun.subscription_fk == sub.id)).scalars()}
    assert statuses[revised.name] == "applied" and statuses[src.name] == "superseded"

    # an OLDER run arriving late never overwrites newer data
    stale = _write_run(src, "2026-10-01T06:00:00Z", lambda r: {**r, "costInBillingCurrency": "999.00"})
    sync_subscription(demo_db["session_factory"], sub.id)
    db.expire_all()
    assert _totals(db, sub.id, SEPT[1], SEPT[2]) == (count1, total1)
    st = db.execute(select(ExportRun).where(ExportRun.run_key.like(f"%{stale.name}"))).scalar_one()
    assert st.status == "superseded" and st.days_applied == 0

    # restore with a newer run carrying the original content
    _write_run(src, "2026-10-25T06:00:00Z", extra_newline=True)
    sync_subscription(demo_db["session_factory"], sub.id)
    db.expire_all()
    assert _totals(db, sub.id, SEPT[1], SEPT[2]) == (count0, total0)


def test_failure_in_one_subscription_does_not_block_others(demo_db, db):
    from worker.ingestion.pipeline import IngestionFailure, sync_subscription

    bad_sub, good_sub = _sub(db, 5), _sub(db, 4)
    root = demo_db["root"]
    src = _final_run_dir(root, bad_sub.subscription_id, SEPT[0])
    before = _totals(db, bad_sub.id, SEPT[1], SEPT[2])
    broken = _write_run(src, "2026-10-21T06:00:00Z", header_override=["date", "SubscriptionId", "meterName"])  # no cost column
    try:
        with pytest.raises(IngestionFailure):
            sync_subscription(demo_db["session_factory"], bad_sub.id)
        # other subscription still syncs fine
        assert sync_subscription(demo_db["session_factory"], good_sub.id)["runs_failed"] == 0
        db.expire_all()
        assert _totals(db, bad_sub.id, SEPT[1], SEPT[2]) == before  # failed run changed nothing
        run = db.execute(select(ExportRun).where(ExportRun.run_key.like(f"%{broken.name}"))).scalar_one()
        assert run.status == "failed" and "missing required column" in run.error
        assert db.get(AzureSubscription, bad_sub.id).last_sync_error
    finally:
        shutil.rmtree(broken)
        sync_subscription(demo_db["session_factory"], bad_sub.id)
        db.expire_all()
        assert db.get(AzureSubscription, bad_sub.id).last_sync_error is None


def test_rejected_rows_above_threshold_fail_the_run(demo_db, db):
    from worker.ingestion.pipeline import IngestionFailure, sync_subscription

    sub = _sub(db, 3)
    src = _final_run_dir(demo_db["root"], sub.subscription_id, SEPT[0])
    before = _totals(db, sub.id, SEPT[1], SEPT[2])
    n = {"i": 0}

    def corrupt(r):
        n["i"] += 1
        if n["i"] % 5 == 0:
            r["date"] = "31/31/2026"
        return r

    bad = _write_run(src, "2026-10-22T06:00:00Z", corrupt)
    try:
        with pytest.raises(IngestionFailure):
            sync_subscription(demo_db["session_factory"], sub.id)
        db.expire_all()
        assert _totals(db, sub.id, SEPT[1], SEPT[2]) == before
        errs = db.execute(text("SELECT COUNT(*) FROM ingestion_errors WHERE error_type='invalid_date'")).scalar_one()
        assert errs > 0
    finally:
        shutil.rmtree(bad)
        sync_subscription(demo_db["session_factory"], sub.id)


def test_every_record_traceable_to_source_file(db):
    missing = db.execute(select(func.count()).select_from(CostRecord).where((CostRecord.ingestion_file_id.is_(None)) | (CostRecord.source_row_number.is_(None)))).scalar_one()
    assert missing == 0
