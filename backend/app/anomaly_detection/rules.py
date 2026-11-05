"""Transparent, rule-based anomaly detection primitives (pure functions).

Each detector combines *relative* significance (percentage over baseline) with *absolute*
financial significance (minimum currency increase) so that a 500% jump on a $2 resource
does not raise an alert while a $10,000 jump does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median as _median
from typing import Any

from app.analytics.comparison import HUNDRED, ZERO, to_decimal
from app.analytics.periods import add_months, month_start

SEVERITIES = ["informational", "low", "medium", "high", "critical"]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

DEFAULT_SEVERITY_THRESHOLDS = [
    {"severity": "critical", "min_abs": 5000, "min_pct": 50},
    {"severity": "high", "min_abs": 2000, "min_pct": 30},
    {"severity": "medium", "min_abs": 500, "min_pct": 20},
    {"severity": "low", "min_abs": 100, "min_pct": 10},
]
SENSITIVITY_MULTIPLIER = {"low": Decimal("1.5"), "medium": Decimal("1.0"), "high": Decimal("0.67")}

BASELINE_LABELS = {
    "same_weekday_median": "median of the same weekday over the previous {n} weeks",
    "rolling_median": "median of the previous {n} days",
    "rolling_mean": "mean of the previous {n} days",
    "previous_weeks_mean": "mean of the previous {n} weekly totals",
    "previous_month_equivalent": "same elapsed days of the previous month",
    "first_week_of_window": "first week of a {n}-week window",
    "none": "no prior spend (new resource)",
}


@dataclass
class Detection:
    observed: Decimal
    baseline: Decimal
    previous: Decimal
    period_start: date
    period_end: date
    baseline_method: str
    baseline_window: int
    baseline_points: list[tuple[str, Decimal]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def abs_increase(self) -> Decimal:
        return self.observed - self.baseline

    @property
    def pct_increase(self) -> Decimal | None:
        if self.baseline == ZERO:
            return None
        return (self.observed - self.baseline) / abs(self.baseline) * HUNDRED

    @property
    def baseline_description(self) -> str:
        return BASELINE_LABELS.get(self.baseline_method, self.baseline_method).format(n=self.baseline_window)


def median(values: list[Decimal]) -> Decimal:
    if not values:
        return ZERO
    return to_decimal(_median(values))


def _val(series: dict[date, Decimal], d: date) -> Decimal:
    return to_decimal(series.get(d, ZERO))


def _window_sum(series: dict[date, Decimal], end: date, days: int) -> Decimal:
    return sum((_val(series, end - timedelta(days=i)) for i in range(days)), ZERO)


def history_days(series: dict[date, Decimal], before: date, lookback: int) -> int:
    """Number of days with billing records in the ``lookback`` days before ``before``."""
    return sum(1 for i in range(1, lookback + 1) if (before - timedelta(days=i)) in series)


def daily_baseline(series: dict[date, Decimal], target: date, method: str, window: int) -> tuple[Decimal, list[tuple[str, Decimal]]]:
    if method == "same_weekday_median":
        pts = [target - timedelta(days=7 * k) for k in range(1, window + 1)]
        values = [_val(series, d) for d in pts]
        return median(values), [(d.isoformat(), v) for d, v in zip(pts, values, strict=False)]
    pts = [target - timedelta(days=k) for k in range(1, window + 1)]
    values = [_val(series, d) for d in pts]
    if method == "rolling_median":
        return median(values), [(d.isoformat(), v) for d, v in zip(pts, values, strict=False)]
    if method == "rolling_mean":
        return (sum(values, ZERO) / Decimal(len(values)) if values else ZERO), [(d.isoformat(), v) for d, v in zip(pts, values, strict=False)]
    raise ValueError(f"Unknown baseline method '{method}'")


def _significant(observed: Decimal, baseline: Decimal, pct_threshold: Decimal, min_abs: Decimal) -> bool:
    inc = observed - baseline
    if inc < min_abs or baseline <= ZERO:
        return False
    return inc / baseline * HUNDRED >= pct_threshold


def detect_daily_spike(
    series: dict[date, Decimal],
    target: date,
    *,
    method: str = "same_weekday_median",
    window: int = 4,
    pct_threshold: Decimal | float = 25,
    min_abs: Decimal | float = 200,
    min_history_days: int = 14,
) -> Detection | None:
    if target not in series:
        return None
    lookback = 7 * window if method == "same_weekday_median" else window
    if history_days(series, target, max(lookback, min_history_days)) < min_history_days:
        return None
    observed = _val(series, target)
    baseline, points = daily_baseline(series, target, method, window)
    if not _significant(observed, baseline, to_decimal(pct_threshold), to_decimal(min_abs)):
        return None
    previous = points[0][1] if points else ZERO
    return Detection(observed, baseline, previous, target, target, method, window, points)


def detect_weekly_spike(
    series: dict[date, Decimal],
    target: date,
    *,
    weeks: int = 4,
    pct_threshold: Decimal | float = 15,
    min_abs: Decimal | float = 750,
) -> Detection | None:
    if history_days(series, target - timedelta(days=6), 7 * weeks) < 7 * weeks - 3:
        return None
    observed = _window_sum(series, target, 7)
    weekly = [_window_sum(series, target - timedelta(days=7 * k), 7) for k in range(1, weeks + 1)]
    baseline = sum(weekly, ZERO) / Decimal(weeks)
    if not _significant(observed, baseline, to_decimal(pct_threshold), to_decimal(min_abs)):
        return None
    points = [((target - timedelta(days=7 * k + 6)).isoformat() + "/" + (target - timedelta(days=7 * k)).isoformat(), v) for k, v in enumerate(weekly, start=1)]
    return Detection(observed, baseline, weekly[0], target - timedelta(days=6), target, "previous_weeks_mean", weeks, points)


def detect_monthly_spike(
    series: dict[date, Decimal],
    target: date,
    *,
    pct_threshold: Decimal | float = 15,
    min_abs: Decimal | float = 2000,
    min_elapsed_days: int = 5,
) -> Detection | None:
    ms = month_start(target)
    elapsed = (target - ms).days + 1
    if elapsed < min_elapsed_days:
        return None
    prev_start = add_months(ms, -1)
    prev_end = min(prev_start + timedelta(days=elapsed - 1), ms - timedelta(days=1))
    if history_days(series, ms, (ms - prev_start).days) < (prev_end - prev_start).days - 2:
        return None
    observed = sum((_val(series, ms + timedelta(days=i)) for i in range(elapsed)), ZERO)
    baseline = sum((_val(series, prev_start + timedelta(days=i)) for i in range((prev_end - prev_start).days + 1)), ZERO)
    if not _significant(observed, baseline, to_decimal(pct_threshold), to_decimal(min_abs)):
        return None
    return Detection(observed, baseline, baseline, ms, target, "previous_month_equivalent", elapsed,
                     [(f"{prev_start.isoformat()}/{prev_end.isoformat()}", baseline)])


def detect_continuous_increase(
    series: dict[date, Decimal],
    target: date,
    *,
    weeks: int = 4,
    min_step_pct: Decimal | float = 3,
    min_abs: Decimal | float = 300,
) -> Detection | None:
    """``weeks`` consecutive week-over-week increases (each >= min_step_pct) whose
    cumulative weekly increase is at least ``min_abs``."""
    totals = [_window_sum(series, target - timedelta(days=7 * k), 7) for k in range(weeks, -1, -1)]  # oldest -> newest
    if history_days(series, target - timedelta(days=6), 7 * weeks) < 7 * weeks - 3:
        return None
    step = to_decimal(min_step_pct) / HUNDRED
    for prev, cur in zip(totals, totals[1:], strict=False):
        if prev <= ZERO or cur < prev * (Decimal(1) + step):
            return None
    if totals[-1] - totals[0] < to_decimal(min_abs):
        return None
    points = [((target - timedelta(days=7 * k + 6)).isoformat() + "/" + (target - timedelta(days=7 * k)).isoformat(), v)
              for k, v in zip(range(weeks, -1, -1), totals, strict=False)]
    return Detection(totals[-1], totals[0], totals[-2], target - timedelta(days=6), target, "first_week_of_window", weeks + 1, points,
                     extra={"weekly_totals": [str(t) for t in totals]})


def classify_severity(
    abs_increase: Decimal,
    pct_increase: Decimal | None,
    thresholds: list[dict[str, Any]] | None = None,
    sensitivity: str = "medium",
) -> str:
    thresholds = thresholds or DEFAULT_SEVERITY_THRESHOLDS
    mult = SENSITIVITY_MULTIPLIER.get(sensitivity, Decimal(1))
    abs_increase = to_decimal(abs_increase)
    for t in sorted(thresholds, key=lambda t: -SEVERITY_RANK.get(t["severity"], 0)):
        if abs_increase >= to_decimal(t["min_abs"]) * mult and (pct_increase is None or pct_increase >= to_decimal(t.get("min_pct", 0))):
            return t["severity"]
    return "informational"


def scaled(value: Any, sensitivity: str) -> Decimal:
    return to_decimal(value) * SENSITIVITY_MULTIPLIER.get(sensitivity, Decimal(1))


RECOMMENDED_STEPS: dict[str, list[str]] = {
    "Azure Kubernetes Service": [
        "Review node pool node counts and cluster autoscaler events for the affected dates.",
        "Check for new deployments, increased replica counts or pending pods that triggered scale-out.",
        "Compare VM hours by node pool meter in the meter breakdown below.",
        "Review the Azure Activity Log for node pool or cluster configuration changes.",
    ],
    "Virtual Machines": [
        "Confirm whether new VMs were created or existing VMs resized (Activity Log).",
        "Check whether VMs that are normally deallocated were left running.",
        "Review reservation / savings plan coverage for the affected VM sizes.",
    ],
    "Azure SQL": [
        "Check for service tier, vCore or DTU changes on the affected databases (Activity Log).",
        "Review storage growth and backup storage consumption.",
        "Confirm whether elastic pool or serverless auto-scaling increased capacity.",
    ],
    "Storage": [
        "Review capacity growth per storage account and container.",
        "Check lifecycle management policies and blob tier distribution (Hot / Cool / Archive).",
        "Review transaction volume and geo-replication settings.",
    ],
    "Networking": [
        "Review outbound data transfer volume (egress) and its destinations.",
        "Check for new cross-region traffic, VPN / ExpressRoute changes or new public endpoints.",
        "Use NSG flow logs or Traffic Analytics to identify high-volume sources.",
    ],
    "Azure Monitor": [
        "Review Log Analytics ingestion volume by table and by source resource.",
        "Check recently enabled diagnostic settings or verbose application logging.",
        "Review retention and data collection rules; consider Basic Logs for verbose tables.",
    ],
    "App Service": [
        "Check App Service plan scale-out (instance count) and tier changes.",
        "Review autoscale rules and recent deployments.",
    ],
    "_default": [
        "Review the meter breakdown to identify which billing meters changed.",
        "Check the Azure Activity Log for resource creation or configuration changes on the affected dates.",
        "Confirm with the resource owner whether the change was expected.",
    ],
    "_non_production": [
        "Confirm with the owning team whether Non-Production activity (load test, migration, new environment) was planned.",
    ],
    "_new_resource": [
        "Identify who created the resource (Activity Log 'Create' operation) and confirm it is expected.",
        "Verify the resource SKU and size match the intended workload.",
        "Ensure the resource is tagged with owner and cost center.",
    ],
}
