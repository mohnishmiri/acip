from datetime import date

import pytest

pytestmark = pytest.mark.integration


def test_retention_drops_only_whole_expired_partitions(db):
    from sqlalchemy import text

    from app.services import settings_service
    from worker.aggregation.retention import apply_retention

    before_agg = db.execute(text("SELECT SUM(cost) FROM monthly_cost_aggregates WHERE dataset_type='actual'")).scalar_one()
    settings_service.set_setting(db, "retention.cost_records_months", 20, "test")
    out = apply_retention(db, today=date(2026, 11, 6))  # cutoff 2025-03-01 -> Jan & Feb 2025 dropped
    assert set(out["dropped"]) == {"cost_records_2025_01", "cost_records_2025_02"}
    assert db.execute(text("SELECT MIN(usage_date) FROM cost_records")).scalar_one() >= date(2025, 3, 1)
    assert db.execute(text("SELECT SUM(cost) FROM monthly_cost_aggregates WHERE dataset_type='actual'")).scalar_one() == before_agg
    db.rollback()  # DDL is transactional in PostgreSQL: partitions restored
    settings_service.invalidate_cache()
