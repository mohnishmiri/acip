"""Cost forecasting.

Three transparent methods (the selected method is always reported with the result):

* ``run_rate``  -- average daily run-rate of the period so far.
* ``recent``    -- average of the most recent ``recent_days`` days.
* ``trend``     -- ordinary least-squares linear trend over the last ``trend_days`` days.

Forecasts are projections and are always returned separately from actual cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.analytics.comparison import ZERO, to_decimal

METHODS = {
    "run_rate": "Average daily run-rate (period to date)",
    "recent": "Recent daily spending (last 7 days)",
    "trend": "Historical linear trend (last 60 days)",
}


@dataclass
class ForecastResult:
    method: str
    method_label: str
    period_start: date
    period_end: date
    as_of: date
    actual_to_date: Decimal
    projected_remaining: Decimal
    forecast_total: Decimal
    daily_rate: Decimal
    elapsed_days: int
    remaining_days: int
    projection: list[tuple[date, Decimal]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _sum_range(daily: dict[date, Decimal], start: date, end: date) -> Decimal:
    total = ZERO
    d = start
    while d <= end:
        total += to_decimal(daily.get(d, ZERO))
        d += timedelta(days=1)
    return total


def forecast_period(
    daily: dict[date, Decimal],
    *,
    as_of: date,
    period_start: date,
    period_end: date,
    method: str = "run_rate",
    recent_days: int = 7,
    trend_days: int = 60,
) -> ForecastResult:
    if method not in METHODS:
        raise ValueError(f"Unknown forecast method '{method}'")
    notes: list[str] = []
    as_of_eff = min(max(as_of, period_start - timedelta(days=1)), period_end)
    elapsed = max((as_of_eff - period_start).days + 1, 0)
    remaining = (period_end - as_of_eff).days
    actual = _sum_range(daily, period_start, as_of_eff) if elapsed else ZERO

    projection: list[tuple[date, Decimal]] = []
    rate = ZERO
    if remaining > 0:
        if method == "run_rate":
            if elapsed > 0:
                rate = actual / Decimal(elapsed)
            else:
                rate = _sum_range(daily, as_of - timedelta(days=recent_days - 1), as_of) / Decimal(recent_days)
                notes.append("No days elapsed in the period yet; used the recent daily average.")
            projection = [(as_of_eff + timedelta(days=i), rate) for i in range(1, remaining + 1)]
        elif method == "recent":
            rate = _sum_range(daily, as_of - timedelta(days=recent_days - 1), as_of) / Decimal(recent_days)
            projection = [(as_of_eff + timedelta(days=i), rate) for i in range(1, remaining + 1)]
        else:
            start = as_of - timedelta(days=trend_days - 1)
            points = [(i, to_decimal(daily.get(start + timedelta(days=i), ZERO))) for i in range(trend_days)]
            observed = [p for p in points if (start + timedelta(days=p[0])) in daily]
            if len(observed) < 14:
                notes.append("Fewer than 14 days of history; fell back to the period run-rate.")
                rate = actual / Decimal(elapsed) if elapsed else ZERO
                projection = [(as_of_eff + timedelta(days=i), rate) for i in range(1, remaining + 1)]
            else:
                n = Decimal(len(points))
                sx = sum(Decimal(x) for x, _ in points)
                sy = sum(y for _, y in points)
                sxx = sum(Decimal(x) * Decimal(x) for x, _ in points)
                sxy = sum(Decimal(x) * y for x, y in points)
                denom = n * sxx - sx * sx
                slope = (n * sxy - sx * sy) / denom if denom != 0 else ZERO
                intercept = (sy - slope * sx) / n
                offset = (as_of_eff - start).days
                for i in range(1, remaining + 1):
                    v = intercept + slope * Decimal(offset + i)
                    projection.append((as_of_eff + timedelta(days=i), max(v, ZERO)))
                rate = (sum((v for _, v in projection), ZERO) / Decimal(remaining)) if remaining else ZERO
                if any(v == ZERO for _, v in projection):
                    notes.append("Trend projected below zero for some days; those days were floored at zero.")
    projected = sum((v for _, v in projection), ZERO)
    return ForecastResult(
        method=method,
        method_label=METHODS[method],
        period_start=period_start,
        period_end=period_end,
        as_of=as_of_eff,
        actual_to_date=actual,
        projected_remaining=projected,
        forecast_total=actual + projected,
        daily_rate=rate,
        elapsed_days=elapsed,
        remaining_days=remaining,
        projection=projection,
        notes=notes,
    )


def budget_status(amount: Decimal, actual: Decimal, forecast: Decimal | None) -> dict:
    """Budget utilisation figures. Utilisation is None (not infinity) for a zero budget."""
    amount, actual = to_decimal(amount), to_decimal(actual)
    utilization = (actual / amount * 100) if amount != ZERO else None
    remaining = amount - actual
    forecast_variance = (to_decimal(forecast) - amount) if forecast is not None else None
    forecast_utilization = (to_decimal(forecast) / amount * 100) if (forecast is not None and amount != ZERO) else None
    return {
        "amount": amount,
        "actual": actual,
        "remaining": remaining,
        "utilization_pct": utilization,
        "forecast": forecast,
        "forecast_variance": forecast_variance,
        "forecast_utilization_pct": forecast_utilization,
    }
