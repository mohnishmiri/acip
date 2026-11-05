"""Post-ingestion analytics: anomalies -> savings -> budgets/forecasts -> notifications."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.anomaly_detection.engine import AnomalyEngine
from app.models import ForecastRecord
from app.services import budget_service, freshness_service, notification_service, savings_service

log = logging.getLogger(__name__)


def run_analytics(db: Session, *, lookback_days: int | None = None, notify: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {}
    stats = AnomalyEngine(db, "actual").run(lookback_days=lookback_days)
    result["anomalies"] = {k: v for k, v in stats.items() if k != "new_anomaly_ids"} | {"new": len(stats["new_anomaly_ids"])}
    db.flush()

    sav = savings_service.evaluate_savings(db)
    result["savings"] = {"created": sav["created"], "evaluated": sav["evaluated"]}
    db.flush()

    budgets = budget_service.list_budgets(db)
    today = datetime.now(UTC).date()
    for b in budgets:
        db.add(ForecastRecord(
            generated_on=today, as_of_date=datetime.fromisoformat(b["as_of"]).date(), scope_type=f"budget:{b['scope_type']}",
            scope_ref=b["scope_ref"], dataset_type=b["cost_type"], billing_currency=b["currency"], method=b["forecast_method"],
            period_start=datetime.fromisoformat(b["period_start"]).date(), period_end=datetime.fromisoformat(b["period_end"]).date(),
            actual_to_date=b["actual"], forecast_total=b["forecast"], details={"budget_id": b["id"], "amount": b["amount"]},
        ))
    result["budgets_evaluated"] = len(budgets)

    if notify:
        result["notifications"] = {
            "anomaly": notification_service.alert_for_anomalies(db, stats["new_anomaly_ids"]),
            "budget": notification_service.alert_for_budgets(db, budgets),
            "data_delay": notification_service.alert_for_data_delay(db, freshness_service.subscription_freshness(db)),
            "savings": notification_service.alert_for_savings(db, sav["created_ids"]),
        }
    return result
