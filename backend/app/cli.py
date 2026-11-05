"""Operational CLI.

    python -m app.cli init            # wait for DB, migrate, seed reference data, register subscriptions, seed demo if enabled
    python -m app.cli migrate         # alembic upgrade head
    python -m app.cli seed-demo       # (re)generate and ingest DEMO DATA
    python -m app.cli reset-demo      # remove DEMO DATA
    python -m app.cli analytics       # run anomaly detection / savings / budget alerts now
    python -m app.cli test-connections
    python -m app.cli dump-schema     # print the schema DDL to stdout (requires pg_dump)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine, session_scope
from app.core.logging import configure_logging

log = logging.getLogger("acip.cli")


def wait_for_db(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with get_engine().connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            if time.time() > deadline:
                raise SystemExit(f"Database not reachable: {exc}") from exc
            log.info("Waiting for database…")
            time.sleep(2)


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    command.upgrade(cfg, "head")


def init() -> dict:
    from app.demo.seed import demo_present, seed_demo
    from app.services.seed_service import seed_reference_data
    from app.services.subscription_service import load_config_file

    wait_for_db()
    migrate()
    out: dict = {}
    with session_scope() as db:
        out["reference"] = seed_reference_data(db)
        out["config"] = load_config_file(db)
        demo = demo_present(db)
    if get_settings().demo_mode and not demo:
        log.info("Seeding DEMO DATA (first start)…")
        out["demo"] = seed_demo()
    return out


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    configure_logging(s.log_level, "text")
    p = argparse.ArgumentParser(prog="acip")
    p.add_argument("command", choices=["init", "migrate", "seed-demo", "reset-demo", "analytics", "retention", "test-connections", "dump-schema"])
    p.add_argument("--lookback-days", type=int, default=None)
    args = p.parse_args(argv)
    if args.command == "init":
        result = init()
    elif args.command == "migrate":
        wait_for_db()
        migrate()
        result = {"migrated": True}
    elif args.command == "seed-demo":
        from app.demo.seed import reset_demo, seed_demo
        from app.services.seed_service import seed_reference_data

        wait_for_db()
        migrate()
        with session_scope() as db:
            seed_reference_data(db)
        reset_demo()
        result = seed_demo(force_regenerate=True)
    elif args.command == "reset-demo":
        from app.demo.seed import reset_demo

        result = reset_demo()
    elif args.command == "analytics":
        from app.services.analytics_runner import run_analytics

        with session_scope() as db:
            result = run_analytics(db, lookback_days=args.lookback_days)
    elif args.command == "retention":
        from worker.aggregation.retention import apply_retention

        with session_scope() as db:
            result = apply_retention(db)
    elif args.command == "test-connections":
        from app.services.connection_service import test_all

        with session_scope() as db:
            result = {"results": test_all(db)}
    else:
        import subprocess

        from sqlalchemy.engine import make_url

        url = make_url(s.database_url)
        env = {"PGPASSWORD": url.password or ""}
        sql = subprocess.run(
            ["pg_dump", "--schema-only", "--no-owner", "-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "", url.database or ""],
            capture_output=True, text=True, env=env, check=True,
        ).stdout
        sys.stdout.write(sql)  # redirect on the host: ... python -m app.cli dump-schema > database/schema/schema.sql
        return 0
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
