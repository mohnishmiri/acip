"""Local export mode: Cost Details API -> local export folder (Azure layout) -> ingestion."""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.integration
GUID = "f0000000-0000-4000-8000-00000000aaaa"


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, date, date]] = []

    def generate_cost_details(self, subscription_id, metric, start, end):
        self.calls.append((metric, start, end))
        if start.month == 8:
            return []  # Azure reports no data for August
        return [f"https://example.invalid/{metric}/{start.isoformat()}/{end.isoformat()}"]


def fake_download(scale: Decimal):
    def _dl(url: str, target: Path) -> int:
        _, _, _, metric, s, e = url.split("/")
        start, end = date.fromisoformat(s), date.fromisoformat(e)
        rows = []
        d = start
        while d <= end:
            rows.append({"date": d.strftime("%m/%d/%Y"), "SubscriptionId": GUID, "costInBillingCurrency": f"{Decimal('10.00') * scale:.2f}", "billingCurrency": "USD",
                         "meterCategory": "Storage", "ResourceId": f"/subscriptions/{GUID}/resourceGroups/rg-local/providers/Microsoft.Storage/storageAccounts/stlocal"})
            d = date.fromordinal(d.toordinal() + 1)
        with open(target, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return len(rows)
    return _dl


def test_local_export_layout_ingestion_and_repull(demo_db, monkeypatch):
    from app.core.db import session_factory
    from app.models import ExportRun
    from app.services.subscription_service import upsert_subscription
    from worker.ingestion import local_export
    from worker.ingestion.pipeline import sync_subscription

    sf = session_factory()
    with sf() as db:
        sub = upsert_subscription(db, {"subscription_id": GUID, "subscription_name": "LOCAL-Test", "environment": "unallocated", "billing_currency": "USD"})
        db.commit()
        sid = sub.id
    root: Path = demo_db["root"]

    monkeypatch.setattr(local_export, "_download", fake_download(Decimal(1)))
    client = FakeClient()
    out = local_export.pull_subscription(sf, sid, date(2026, 8, 1), date(2026, 10, 15), ["actual"], client=client)
    assert [c[1:] for c in client.calls] == [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 15))]
    assert out["files"] == 2 and out["rows"] == 30 + 15
    assert next(r for r in out["runs"] if r["month"] == "2026-08")["files"] == 0  # empty month skipped, not an empty run

    base = root / "cost-exports" / "subscriptions" / GUID / "actual" / "acip-actual-daily"
    assert sorted(p.name for p in base.iterdir()) == ["20260901-20260930", "20261001-20261031"]
    manifest = json.loads(next((base / "20261001-20261031").glob("*/manifest.json")).read_text())
    assert manifest["runInfo"]["startDate"].startswith("2026-10-01") and manifest["dataRowCount"] == 15

    res = sync_subscription(sf, sid, dataset_types=["actual"])
    assert res["runs_applied"] == 2 and res["rows_loaded"] == 45
    with sf() as db:
        total = db.execute(text("SELECT SUM(cost) FROM cost_records WHERE subscription_fk=:s"), {"s": sid}).scalar_one()
        assert total == Decimal("450.00")

    # Re-pull October with revised values: the newer run replaces October; September is untouched.
    monkeypatch.setattr(local_export, "_download", fake_download(Decimal(2)))
    local_export.pull_subscription(sf, sid, date(2026, 10, 1), date(2026, 10, 15), ["actual"], client=FakeClient())
    sync_subscription(sf, sid, dataset_types=["actual"])
    with sf() as db:
        rows, total = db.execute(text("SELECT COUNT(*), SUM(cost) FROM cost_records WHERE subscription_fk=:s"), {"s": sid}).one()
        assert rows == 45 and total == Decimal("300.00") + Decimal("300.00")  # Sep 30 x 10 + Oct 15 x 20
        statuses = sorted(r.status for r in db.execute(select(ExportRun).where(ExportRun.subscription_fk == sid)).scalars())
        assert statuses == ["applied", "applied", "superseded"]
        db.execute(text("DELETE FROM cost_records WHERE subscription_fk=:s"), {"s": sid})
        db.execute(text("DELETE FROM daily_cost_aggregates WHERE subscription_fk=:s"), {"s": sid})
        db.commit()


def test_local_export_refuses_demo_subscriptions(demo_db):
    from app.core.db import session_factory
    from worker.ingestion.local_export import LocalExportError, pull_subscription

    with pytest.raises(LocalExportError):
        pull_subscription(session_factory(), demo_db["subscription_fks"][0], date(2026, 10, 1), date(2026, 10, 2), ["actual"], client=FakeClient())


def test_category_rule_upgrade_adds_new_defaults_once(demo_db):
    from sqlalchemy import func

    from app.core.db import session_factory
    from app.models import ApplicationSetting, ServiceCategoryRule
    from app.services.seed_service import CATEGORY_RULES_VERSION_KEY, seed_reference_data

    sf = session_factory()
    with sf() as db:
        # simulate a database seeded before v2: drop v2 rules and the version marker
        db.execute(text("DELETE FROM service_category_rules WHERE priority > 99"))
        db.execute(text("DELETE FROM application_settings WHERE key = :k"), {"k": CATEGORY_RULES_VERSION_KEY})
        db.commit()
        assert seed_reference_data(db)["category_rules"] > 0
        db.commit()
        n = db.execute(select(func.count()).select_from(ServiceCategoryRule)).scalar_one()
        # an administrator deletes one new default; re-running the seed must not re-create it
        db.execute(text("DELETE FROM service_category_rules WHERE pattern = 'event hubs'"))
        db.commit()
        assert seed_reference_data(db)["category_rules"] == 0
        db.commit()
        assert db.execute(select(func.count()).select_from(ServiceCategoryRule)).scalar_one() == n - 1
        assert db.get(ApplicationSetting, CATEGORY_RULES_VERSION_KEY).value == 2
