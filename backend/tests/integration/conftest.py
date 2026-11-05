"""Integration fixtures: a throw-away PostgreSQL database loaded through the real pipeline.

Requires TEST_DATABASE_URL, e.g.
    postgresql+psycopg://acip:acip_local_dev@postgres:5432/acip_test
The database is dropped and recreated for each test session.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

FIXED_TODAY = date(2026, 11, 6)  # Friday -> demo as-of Sunday 2026-11-01
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

if not TEST_DB_URL:
    pytest.skip("TEST_DATABASE_URL not set; skipping integration tests", allow_module_level=True)


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    url = make_url(TEST_DB_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    root = tmp_path_factory.mktemp("exports")
    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ["LOCAL_EXPORT_ROOT"] = str(root)
    os.environ["APP_AUTH_MODE"] = "disabled"
    os.environ["AZURE_AUTH_MODE"] = "disabled"
    from app.core.config import get_settings
    from app.core.db import reset_engine

    get_settings.cache_clear()
    reset_engine()

    from app.cli import migrate
    from app.core.db import session_factory, session_scope
    from app.demo.generator import generate_demo_exports
    from app.demo.seed import create_demo_advisor_recommendations, create_demo_budgets, register_demo_configuration
    from app.models import AzureSubscription
    from app.services.analytics_runner import run_analytics
    from app.services.seed_service import seed_reference_data
    from worker.ingestion.pipeline import sync_subscription

    migrate()
    with session_scope() as db:
        seed_reference_data(db)
        register_demo_configuration(db)
    summary = generate_demo_exports(root, today=FIXED_TODAY)
    sf = session_factory()
    with session_scope() as db:
        subs = [s.id for s in db.execute(select(AzureSubscription).order_by(AzureSubscription.id)).scalars()]
    for sid in subs:
        sync_subscription(sf, sid)
    with session_scope() as db:
        create_demo_budgets(db)
        create_demo_advisor_recommendations(db)
    with session_scope() as db:
        run_analytics(db, lookback_days=60)
    return {"root": root, "summary": summary, "subscription_fks": subs, "session_factory": sf}


@pytest.fixture(scope="session")
def client(demo_db):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def db(demo_db):
    from app.core.db import session_factory

    s = session_factory()()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
