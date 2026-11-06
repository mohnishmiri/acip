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
from app.core.db import get_engine, session_scope, use_batch_mode
from app.core.logging import configure_logging

log = logging.getLogger("acip.cli")


CREDENTIALS_HELP = r"""
Database login failed: {error}

PostgreSQL stores the user's password only when its data volume is FIRST created. If
POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (in .env or your shell) changed after that,
the containers now connect with credentials the existing database does not accept.

Fix one of these ways:
  * keep the data -- set the stored password to the value now in .env:
        docker compose up -d postgres
        docker compose exec -T postgres sh -c 'echo "ALTER USER $POSTGRES_USER WITH PASSWORD :'"'"'pw'"'"';" | psql -U "$POSTGRES_USER" -d postgres -v pw="$POSTGRES_PASSWORD"'
  * start fresh (local demo data is regenerated automatically):
        docker compose down -v && docker compose up --build
"""


def wait_for_db(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with get_engine().connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            # Wrong credentials never fix themselves -- fail fast with an explanation instead of retrying.
            if "password authentication failed" in msg or ("does not exist" in msg and ("role" in msg or "database" in msg)):
                raise SystemExit(CREDENTIALS_HELP.format(error=msg.strip().splitlines()[0])) from exc
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
        if get_settings().effective_export_source == "local":
            from worker.ingestion.local_export import ensure_local_containers

            out["local_export_folders_created"] = ensure_local_containers(db)
    if get_settings().demo_mode and not demo:
        log.info("Seeding DEMO DATA (first start)…")
        out["demo"] = seed_demo()
    return out


def export_local(args) -> dict:
    """Pull cost data with the Cost Details API into the local export folder, then ingest it."""
    from sqlalchemy import select

    from app.core.db import session_factory
    from app.models import AzureSubscription
    from app.services.analytics_runner import run_analytics
    from worker.ingestion.local_export import default_range, pull_subscription
    from worker.ingestion.pipeline import IngestionFailure, sync_subscription

    s = get_settings()
    if not s.azure_enabled:
        raise SystemExit("AZURE_AUTH_MODE is disabled; set it (e.g. client_secret) to call the Cost Details API.")
    if s.effective_export_source != "local":
        raise SystemExit("Set EXPORT_SOURCE=local to use local export mode.")
    start, end = default_range(args.months)
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    sf = session_factory()
    with sf() as db:
        subs = [x for x in db.execute(select(AzureSubscription).where(AzureSubscription.enabled.is_(True), AzureSubscription.is_demo.is_(False)).order_by(AzureSubscription.id)).scalars()
                if not args.subscription or x.subscription_id in {g.lower() for g in args.subscription}]
    results = []
    for sub in subs:  # one subscription at a time; a failure never stops the others
        print(f"[{sub.subscription_name}] pulling {start} .. {end} ({', '.join(datasets)})", flush=True)
        try:
            r = pull_subscription(sf, sub.id, start, end, datasets)
            if not args.no_ingest:
                ing = sync_subscription(sf, sub.id, dataset_types=datasets)
                r["ingested_runs"], r["rows_loaded"] = ing["runs_applied"], ing["rows_loaded"]
            print(f"[{sub.subscription_name}] {r['files']} file(s), {r['rows']} row(s)", flush=True)
            results.append(r)
        except (IngestionFailure, Exception) as exc:  # noqa: BLE001
            print(f"[{sub.subscription_name}] FAILED: {exc}", flush=True)
            results.append({"subscription": sub.subscription_name, "error": str(exc)})
    if not args.no_ingest:
        with session_scope() as db:
            run_analytics(db)
    return {"range": [start.isoformat(), end.isoformat()], "results": results}


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    configure_logging(s.log_level, "text")
    use_batch_mode()
    p = argparse.ArgumentParser(prog="acip")
    p.add_argument("command", choices=["init", "migrate", "seed-demo", "reset-demo", "analytics", "retention", "test-connections", "export-local", "dump-schema"])
    p.add_argument("--lookback-days", type=int, default=None)
    p.add_argument("--months", type=int, default=3, help="export-local: calendar months ending with the current month (1-13)")
    p.add_argument("--subscription", action="append", default=[], help="export-local: subscription GUID (repeatable; default all enabled)")
    p.add_argument("--datasets", default="actual,amortized", help="export-local: comma-separated datasets")
    p.add_argument("--no-ingest", action="store_true", help="export-local: only write files, do not ingest")
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
    elif args.command == "export-local":
        result = export_local(args)
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
