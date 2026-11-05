"""Runtime business settings stored in ``application_settings`` with code defaults."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.anomaly_detection.rules import DEFAULT_SEVERITY_THRESHOLDS
from app.models import ApplicationSetting

DEFAULT_SETTINGS: dict[str, tuple[Any, str]] = {
    "reporting.week_start_isodow": (1, "First day of the reporting week (1 = Monday … 7 = Sunday)."),
    "reporting.default_currency": ("USD", "Currency shown by default when data contains several billing currencies."),
    "reporting.default_cost_type": ("actual", "Default cost basis: actual or amortized."),
    "reporting.significant_change_pct": (5, "Percentage change below which a movement is treated as normal variation."),
    "reporting.significant_change_abs": (500, "Absolute change (billing currency) below which a movement is treated as normal variation."),
    "reporting.default_waterfall_top_n": (4, "Number of individual contributors shown in waterfall charts before grouping the rest into 'Other'."),
    "freshness.delay_threshold_hours": (48, "Hours after which a subscription's latest usage date is considered delayed."),
    "attribution.precedence": (
        ["resource_group_rule", "subscription", "resource_tag"],
        "Order in which sources are consulted for application / environment. First source with a value wins.",
    ),
    "anomaly.sensitivity": ("medium", "Global anomaly sensitivity: low (fewer alerts), medium, high (more alerts)."),
    "anomaly.severity_thresholds": (DEFAULT_SEVERITY_THRESHOLDS, "Severity bands by absolute increase and minimum percentage."),
    "anomaly.lookback_days": (3, "Usage days re-evaluated after each ingestion (late-arriving data)."),
    "anomaly.exclude_charge_types": (["Purchase", "Refund", "Tax", "RoundingAdjustment"], "Charge types ignored by anomaly detection."),
    "forecast.default_method": ("run_rate", "Default forecast method: run_rate, recent or trend."),
    "savings.nonprod_schedule_hours_per_week": (60, "Assumed operating hours/week for Non-Production schedule-based savings estimates."),
    "savings.min_monthly_cost": (200, "Minimum monthly cost for a resource to be evaluated for savings opportunities."),
    "retention.cost_records_months": (37, "Months of raw billing records retained; older monthly partitions are dropped by the retention job (aggregates are kept). 0 disables."),
}

_cache: dict[str, Any] = {}
_cache_at: float = 0.0
_TTL = 15.0


def _load(db: Session) -> dict[str, Any]:
    global _cache, _cache_at
    if time.monotonic() - _cache_at < _TTL and _cache:
        return _cache
    values = {k: v for k, (v, _) in DEFAULT_SETTINGS.items()}
    for row in db.execute(select(ApplicationSetting)).scalars():
        values[row.key] = row.value
    _cache, _cache_at = values, time.monotonic()
    return values


def invalidate_cache() -> None:
    global _cache_at
    _cache_at = 0.0


def get_setting(db: Session, key: str) -> Any:
    return _load(db).get(key, DEFAULT_SETTINGS.get(key, (None, ""))[0])


def all_settings(db: Session) -> list[dict[str, Any]]:
    values = _load(db)
    out = []
    for key, (default, desc) in DEFAULT_SETTINGS.items():
        out.append({"key": key, "value": values.get(key, default), "default": default, "description": desc})
    return out


def set_setting(db: Session, key: str, value: Any, actor: str) -> None:
    if key not in DEFAULT_SETTINGS:
        raise KeyError(key)
    stmt = insert(ApplicationSetting).values(key=key, value=value, description=DEFAULT_SETTINGS[key][1], updated_by=actor)
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value, "updated_by": actor})
    db.execute(stmt)
    invalidate_cache()


def week_start(db: Session) -> int:
    return int(get_setting(db, "reporting.week_start_isodow"))
