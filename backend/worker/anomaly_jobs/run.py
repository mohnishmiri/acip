from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.services.analytics_runner import run_analytics


def run_analytics_job(sf: sessionmaker[Session], lookback_days: int | None = None) -> dict[str, Any]:
    with sf() as db:
        result = run_analytics(db, lookback_days=lookback_days)
        db.commit()
    return result
