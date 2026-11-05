"""Reporting period resolution.

All periods are inclusive date ranges on the billing-date (UTC usage date) basis.

Relative presets are anchored to an *as-of date*: the latest usage date for which billing
data is available in the requested scope (or an explicit override). Azure cost data lags
by 8-72 hours, so anchoring to the wall clock would make every "current" period look like
a cost drop. The resolved range is always returned to the caller so the UI can show the
exact dates being compared.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Literal

PresetName = Literal[
    "today",
    "yesterday",
    "last_7_days",
    "last_30_days",
    "last_90_days",
    "week_to_date",
    "previous_week",
    "month_to_date",
    "previous_month",
    "quarter_to_date",
    "previous_quarter",
    "year_to_date",
    "previous_year",
    "custom",
]
ComparisonMode = Literal["none", "previous_equivalent", "previous_calendar", "same_period_last_year", "custom"]
Granularity = Literal["daily", "weekly", "monthly"]
PeriodUnit = Literal["day", "week", "month", "quarter", "year", "rolling", "custom"]

PRESETS: dict[str, str] = {
    "today": "Today",
    "yesterday": "Yesterday",
    "last_7_days": "Last 7 Days",
    "last_30_days": "Last 30 Days",
    "last_90_days": "Last 90 Days",
    "week_to_date": "Week-to-Date",
    "previous_week": "Previous Week",
    "month_to_date": "Month-to-Date",
    "previous_month": "Previous Month",
    "quarter_to_date": "Quarter-to-Date",
    "previous_quarter": "Previous Quarter",
    "year_to_date": "Year-to-Date",
    "previous_year": "Previous Year",
    "custom": "Custom Range",
}
COMPARISON_MODES: dict[str, str] = {
    "none": "No Comparison",
    "previous_equivalent": "Previous Equivalent Period",
    "previous_calendar": "Previous Calendar Period",
    "same_period_last_year": "Same Period Last Year",
    "custom": "Custom Comparison Range",
}


class PeriodError(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive
    label: str = ""

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise PeriodError(f"Period end {self.end} is before start {self.start}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def iter_days(self):
        d = self.start
        while d <= self.end:
            yield d
            d += timedelta(days=1)


@dataclass(frozen=True)
class ResolvedPeriod:
    period: Period
    preset: str
    unit: PeriodUnit
    nominal_start: date  # full calendar period (e.g. whole week for week-to-date)
    nominal_end: date
    as_of: date

    @property
    def is_incomplete(self) -> bool:
        return self.period.end < self.nominal_end

    @property
    def elapsed_days(self) -> int:
        return self.period.days

    @property
    def nominal_days(self) -> int:
        return (self.nominal_end - self.nominal_start).days + 1


# ---------------------------------------------------------------------------------------
# calendar helpers
# ---------------------------------------------------------------------------------------

def week_start(d: date, week_start_isodow: int = 1) -> date:
    """First day of the week containing ``d``. ``week_start_isodow``: 1=Mon ... 7=Sun."""
    if not 1 <= week_start_isodow <= 7:
        raise PeriodError("week_start_isodow must be between 1 and 7")
    offset = (d.isoweekday() - week_start_isodow) % 7
    return d - timedelta(days=offset)


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month length."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def quarter_end(d: date) -> date:
    return month_end(add_months(quarter_start(d), 2))


def shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb -> 28 Feb
        return d.replace(year=d.year + years, day=28)


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def describe(start: date, end: date) -> str:
    if start == end:
        return _fmt(start)
    if start.year == end.year:
        return f"{start.strftime('%d %b')} – {_fmt(end)}"
    return f"{_fmt(start)} – {_fmt(end)}"


# ---------------------------------------------------------------------------------------
# preset resolution
# ---------------------------------------------------------------------------------------

def resolve_period(
    preset: str,
    as_of: date,
    *,
    week_start_isodow: int = 1,
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> ResolvedPeriod:
    """Resolve a preset to a concrete inclusive range anchored on ``as_of``."""

    def rp(start: date, end: date, unit: PeriodUnit, nominal_start: date | None = None, nominal_end: date | None = None):
        end_clipped = min(end, as_of) if unit not in ("custom",) else end
        if end_clipped < start:
            end_clipped = start
        return ResolvedPeriod(
            period=Period(start, end_clipped, label=PRESETS.get(preset, preset)),
            preset=preset,
            unit=unit,
            nominal_start=nominal_start or start,
            nominal_end=nominal_end or end,
            as_of=as_of,
        )

    if preset == "today":
        return rp(as_of, as_of, "day")
    if preset == "yesterday":
        d = as_of - timedelta(days=1)
        return rp(d, d, "day")
    if preset in ("last_7_days", "last_30_days", "last_90_days"):
        n = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}[preset]
        return rp(as_of - timedelta(days=n - 1), as_of, "rolling")
    if preset == "week_to_date":
        s = week_start(as_of, week_start_isodow)
        return rp(s, as_of, "week", s, s + timedelta(days=6))
    if preset == "previous_week":
        s = week_start(as_of, week_start_isodow) - timedelta(days=7)
        return rp(s, s + timedelta(days=6), "week")
    if preset == "month_to_date":
        s = month_start(as_of)
        return rp(s, as_of, "month", s, month_end(as_of))
    if preset == "previous_month":
        s = month_start(add_months(month_start(as_of), -1))
        return rp(s, month_end(s), "month")
    if preset == "quarter_to_date":
        s = quarter_start(as_of)
        return rp(s, as_of, "quarter", s, quarter_end(as_of))
    if preset == "previous_quarter":
        s = add_months(quarter_start(as_of), -3)
        return rp(s, quarter_end(s), "quarter")
    if preset == "year_to_date":
        s = date(as_of.year, 1, 1)
        return rp(s, as_of, "year", s, date(as_of.year, 12, 31))
    if preset == "previous_year":
        s = date(as_of.year - 1, 1, 1)
        return rp(s, date(as_of.year - 1, 12, 31), "year")
    if preset == "custom":
        if custom_start is None or custom_end is None:
            raise PeriodError("custom preset requires start_date and end_date")
        if custom_end < custom_start:
            raise PeriodError("end_date must not be before start_date")
        clipped_end = min(custom_end, max(as_of, custom_start))
        return ResolvedPeriod(
            period=Period(custom_start, clipped_end, label="Custom Range"),
            preset="custom",
            unit="custom",
            nominal_start=custom_start,
            nominal_end=custom_end,
            as_of=as_of,
        )
    raise PeriodError(f"Unknown date preset '{preset}'")


def resolve_comparison(
    current: ResolvedPeriod,
    mode: str,
    *,
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> Period | None:
    """Resolve the comparison period for ``current``.

    previous_equivalent  -- the previous period of the same unit, covering the same number of
                            elapsed days (e.g. Mon-Wed of last week for a 3-day week-to-date).
    previous_calendar    -- the complete previous calendar period (whole previous week/month).
    same_period_last_year-- the same dates one year earlier.
    custom               -- explicit range.
    """
    p = current.period
    if mode in (None, "", "none"):
        return None
    if mode == "custom":
        if custom_start is None or custom_end is None:
            raise PeriodError("custom comparison requires compare_start_date and compare_end_date")
        return Period(custom_start, custom_end, label="Custom Comparison")
    if mode == "same_period_last_year":
        return Period(shift_years(p.start, -1), shift_years(p.end, -1), label="Same Period Last Year")
    if mode not in ("previous_equivalent", "previous_calendar"):
        raise PeriodError(f"Unknown comparison mode '{mode}'")

    full = mode == "previous_calendar"
    unit = current.unit
    elapsed = p.days

    if unit == "day":
        d = p.start - timedelta(days=1)
        return Period(d, d, label="Previous Day")
    if unit == "week":
        s = current.nominal_start - timedelta(days=7)
        e = s + timedelta(days=6) if full else s + timedelta(days=elapsed - 1)
        return Period(s, e, label="Previous Week" if full else "Previous Week (equivalent days)")
    if unit in ("month", "quarter", "year"):
        months = {"month": 1, "quarter": 3, "year": 12}[unit]
        s = add_months(current.nominal_start, -months)
        if unit == "month":
            unit_end = month_end(s)
        elif unit == "quarter":
            unit_end = quarter_end(s)
        else:
            unit_end = date(s.year, 12, 31)
        e = unit_end if full else min(s + timedelta(days=elapsed - 1), unit_end)
        names = {"month": "Month", "quarter": "Quarter", "year": "Year"}
        suffix = "" if full or not current.is_incomplete else " (equivalent days)"
        return Period(s, e, label=f"Previous {names[unit]}{suffix}")
    # rolling / custom: the immediately preceding window of equal length
    e = p.start - timedelta(days=1)
    s = e - timedelta(days=elapsed - 1)
    return Period(s, e, label=f"Previous {elapsed} Days")


# ---------------------------------------------------------------------------------------
# bucketing
# ---------------------------------------------------------------------------------------

def bucket_start(d: date, granularity: str, week_start_isodow: int = 1) -> date:
    if granularity == "daily":
        return d
    if granularity == "weekly":
        return week_start(d, week_start_isodow)
    if granularity == "monthly":
        return month_start(d)
    raise PeriodError(f"Unknown granularity '{granularity}'")


def buckets(period: Period, granularity: str, week_start_isodow: int = 1) -> list[date]:
    """Ordered bucket start dates covering ``period`` (first bucket may start before it)."""
    out: list[date] = []
    d = bucket_start(period.start, granularity, week_start_isodow)
    while d <= period.end:
        out.append(d)
        if granularity == "daily":
            d += timedelta(days=1)
        elif granularity == "weekly":
            d += timedelta(days=7)
        else:
            d = add_months(d, 1)
    return out


def with_label(period: Period, label: str) -> Period:
    return replace(period, label=label)
