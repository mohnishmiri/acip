"""Retention: drop raw cost_records monthly partitions older than the configured window.

Only raw billing rows are removed; daily / resource / meter / monthly aggregates are kept,
so long-range reporting continues to work. Disabled when the setting is 0.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.periods import add_months, month_start
from app.services import settings_service

log = logging.getLogger(__name__)
PARTITION_RE = re.compile(r"^cost_records_(\d{4})_(\d{2})$")


def apply_retention(db: Session, today: date | None = None) -> dict[str, Any]:
    months = int(settings_service.get_setting(db, "retention.cost_records_months") or 0)
    if months <= 0:
        return {"dropped": [], "retention_months": months, "note": "retention disabled"}
    cutoff = add_months(month_start(today or datetime.now(UTC).date()), -months)
    rows = db.execute(text("SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'cost_records'")).scalars()
    dropped = []
    for name in rows:
        m = PARTITION_RE.match(name)
        if not m:
            continue
        start = date(int(m.group(1)), int(m.group(2)), 1)
        if add_months(start, 1) <= cutoff:  # whole partition is older than the window
            db.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
            dropped.append(name)
            log.info("Dropped expired billing partition", extra={"partition": name})
    return {"dropped": dropped, "retention_months": months, "cutoff": cutoff.isoformat()}
