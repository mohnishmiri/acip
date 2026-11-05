"""Re-apply allocation / category rules to stored billing records and rebuild aggregates."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.allocation import AllocationEngine
from app.models import AzureSubscription
from worker.aggregation.rebuild import rebuild_all_for_subscription

log = logging.getLogger(__name__)

KEY_COLS = ["resource_group", "resource_key", "resource_type", "meter_category", "meter_subcategory", "meter_name", "service_name",
            "consumed_service", "source_cost_center", "tags"]
OUT_COLS = ["application_id", "environment_id", "allocation_status", "service_category", "owner", "cost_center", "project", "team",
            "business_unit", "workload", "attribution_source"]


def reattribute(sf: sessionmaker[Session], subscription_fk: int | None = None) -> dict[str, Any]:
    stats: dict[str, Any] = {"subscriptions": 0, "combinations": 0, "rows_updated": 0}
    with sf() as db:
        ids = [subscription_fk] if subscription_fk else [s.id for s in db.execute(select(AzureSubscription)).scalars()]
    for sid in ids:
        with sf() as db:
            engine = AllocationEngine.load(db)
            conn = db.connection()
            combos = conn.execute(text(f"SELECT DISTINCT {', '.join(KEY_COLS)} FROM cost_records WHERE subscription_fk = :s"), {"s": sid}).mappings().all()
            conn.execute(text(
                "CREATE TEMP TABLE realloc (resource_group text, resource_key text, resource_type text, meter_category text, meter_subcategory text, "
                "meter_name text, service_name text, consumed_service text, source_cost_center text, tags jsonb, application_id int, environment_id int, "
                "allocation_status text, service_category text, owner text, cost_center text, project text, team text, business_unit text, workload text, "
                "attribution_source text) ON COMMIT DROP"
            ))
            raw = conn.connection.driver_connection
            with raw.cursor() as cur, cur.copy(f"COPY realloc ({', '.join(KEY_COLS + OUT_COLS)}) FROM STDIN") as cp:
                for c in combos:
                    row = dict(c)
                    row["subscription_fk"] = sid
                    row["cost_center_column"] = row.get("source_cost_center")
                    a = engine.allocate(row)
                    cp.write_row([
                        *(json.dumps(c[k]) if k == "tags" and c[k] is not None else c[k] for k in KEY_COLS),
                        a.application_id, a.environment_id, a.allocation_status, a.service_category, a.owner, a.cost_center, a.project,
                        a.team, a.business_unit, a.workload, a.source,
                    ])
            sets = ", ".join(f"{c} = r.{c}" for c in OUT_COLS)
            match = " AND ".join(f"c.{k} IS NOT DISTINCT FROM r.{k}" for k in KEY_COLS if k != "resource_key")
            res = conn.execute(text(f"UPDATE cost_records c SET {sets} FROM realloc r WHERE c.subscription_fk = :s AND c.resource_key = r.resource_key AND {match}"), {"s": sid})
            rebuild_all_for_subscription(conn, sid)
            conn.execute(text(
                "UPDATE azure_resources a SET application_id = r.application_id, environment_id = r.environment_id, allocation_status = r.allocation_status, "
                "service_category = r.service_category, owner = COALESCE(r.owner, a.owner), cost_center = COALESCE(r.cost_center, a.cost_center) "
                "FROM (SELECT DISTINCT ON (resource_key) * FROM realloc WHERE resource_key <> '' ORDER BY resource_key) r WHERE a.resource_key = r.resource_key"
            ))
            db.commit()
            stats["subscriptions"] += 1
            stats["combinations"] += len(combos)
            stats["rows_updated"] += res.rowcount or 0
            log.info("Re-attributed subscription", extra={"subscription_fk": sid, "combinations": len(combos)})
    return stats
