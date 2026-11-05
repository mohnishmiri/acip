"""Rebuild pre-aggregated reporting tables for a (subscription, dataset, date range) slice.

Called inside the same transaction that replaces raw records, so reporting tables are
never observed in a state inconsistent with ``cost_records``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.periods import month_end, month_start

COARSE = [
    "dataset_type",
    "billing_currency",
    "subscription_fk",
    "application_id",
    "environment_id",
    "allocation_status",
    "service_category",
    "region",
    "charge_type",
    "pricing_model",
    "owner",
    "cost_center",
    "is_demo",
]
RESOURCE = COARSE + ["resource_key", "resource_group", "resource_type"]
METER = RESOURCE + ["meter_id", "meter_category", "meter_subcategory", "meter_name", "unit_of_measure", "sku"]

_WHERE = "subscription_fk = :s AND dataset_type = :d AND usage_date BETWEEN :a AND :b"


def rebuild_aggregates(conn: Connection, subscription_fk: int, dataset_type: str, start: date, end: date) -> dict[str, int]:
    p = {"s": subscription_fk, "d": dataset_type, "a": start, "b": end}
    counts: dict[str, int] = {}
    c = ", ".join(COARSE)
    conn.execute(text(f"DELETE FROM daily_cost_aggregates WHERE {_WHERE}"), p)
    r = conn.execute(
        text(
            f"""INSERT INTO daily_cost_aggregates (usage_date, {c}, cost, record_count)
                SELECT usage_date, {c}, SUM(cost), COUNT(*) FROM cost_records WHERE {_WHERE}
                GROUP BY usage_date, {c}"""
        ),
        p,
    )
    counts["daily"] = r.rowcount or 0

    rc = ", ".join(RESOURCE)
    conn.execute(text(f"DELETE FROM resource_cost_aggregates WHERE {_WHERE}"), p)
    r = conn.execute(
        text(
            f"""INSERT INTO resource_cost_aggregates (usage_date, {rc}, resource_name, tags, cost, record_count)
                SELECT usage_date, {rc}, MAX(resource_name),
                       (ARRAY_AGG(tags) FILTER (WHERE tags IS NOT NULL))[1], SUM(cost), COUNT(*)
                  FROM cost_records WHERE {_WHERE}
                 GROUP BY usage_date, {rc}"""
        ),
        p,
    )
    counts["resource"] = r.rowcount or 0

    mc = ", ".join(METER)
    conn.execute(text(f"DELETE FROM meter_cost_aggregates WHERE {_WHERE}"), p)
    r = conn.execute(
        text(
            f"""INSERT INTO meter_cost_aggregates (usage_date, {mc}, resource_name, cost, quantity, record_count)
                SELECT usage_date, {mc}, MAX(resource_name), SUM(cost), SUM(quantity), COUNT(*)
                  FROM cost_records WHERE {_WHERE}
                 GROUP BY usage_date, {mc}"""
        ),
        p,
    )
    counts["meter"] = r.rowcount or 0

    mp = {"s": subscription_fk, "d": dataset_type, "a": month_start(start), "b": month_end(end)}
    conn.execute(text(f"DELETE FROM monthly_cost_aggregates WHERE {_WHERE}"), mp)
    r = conn.execute(
        text(
            f"""INSERT INTO monthly_cost_aggregates (usage_date, {c}, cost, record_count)
                SELECT date_trunc('month', usage_date)::date, {c}, SUM(cost), SUM(record_count)
                  FROM daily_cost_aggregates WHERE {_WHERE}
                 GROUP BY date_trunc('month', usage_date)::date, {c}"""
        ),
        mp,
    )
    counts["monthly"] = r.rowcount or 0
    return counts


def rebuild_all_for_subscription(conn: Connection, subscription_fk: int) -> None:
    rows = conn.execute(
        text("SELECT dataset_type, MIN(usage_date), MAX(usage_date) FROM cost_records WHERE subscription_fk = :s GROUP BY dataset_type"),
        {"s": subscription_fk},
    ).all()
    for dataset_type, lo, hi in rows:
        rebuild_aggregates(conn, subscription_fk, dataset_type, lo, hi)
