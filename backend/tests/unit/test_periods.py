from datetime import date

import pytest

from app.analytics.periods import PeriodError, buckets, resolve_comparison, resolve_period, week_start


def test_week_to_date_incomplete_compares_equivalent_elapsed_days():
    # Wednesday as-of: current week has 3 days of data
    cur = resolve_period("week_to_date", date(2026, 10, 28))
    assert (cur.period.start, cur.period.end) == (date(2026, 10, 26), date(2026, 10, 28))
    assert cur.is_incomplete and cur.elapsed_days == 3 and cur.nominal_days == 7
    prev = resolve_comparison(cur, "previous_equivalent")
    assert (prev.start, prev.end) == (date(2026, 10, 19), date(2026, 10, 21))


def test_week_to_date_full_calendar_alternative():
    cur = resolve_period("week_to_date", date(2026, 10, 28))
    prev = resolve_comparison(cur, "previous_calendar")
    assert (prev.start, prev.end) == (date(2026, 10, 19), date(2026, 10, 25))


def test_configurable_week_start_sunday():
    assert week_start(date(2026, 10, 28), 7) == date(2026, 10, 25)
    cur = resolve_period("week_to_date", date(2026, 10, 28), week_start_isodow=7)
    assert cur.period.start == date(2026, 10, 25)


def test_month_to_date_equivalent_clips_to_shorter_previous_month():
    cur = resolve_period("month_to_date", date(2026, 3, 31))
    prev = resolve_comparison(cur, "previous_equivalent")
    assert (prev.start, prev.end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_previous_month_and_quarter_and_year():
    assert resolve_period("previous_month", date(2026, 1, 15)).period.start == date(2025, 12, 1)
    q = resolve_period("previous_quarter", date(2026, 5, 2))
    assert (q.period.start, q.period.end) == (date(2026, 1, 1), date(2026, 3, 31))
    y = resolve_period("previous_year", date(2026, 5, 2))
    assert (y.period.start, y.period.end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_same_period_last_year_handles_leap_day():
    cur = resolve_period("custom", date(2028, 3, 1), custom_start=date(2028, 2, 29), custom_end=date(2028, 2, 29))
    prev = resolve_comparison(cur, "same_period_last_year")
    assert prev.start == date(2027, 2, 28)


def test_rolling_window_previous_is_immediately_preceding():
    cur = resolve_period("last_30_days", date(2026, 11, 1))
    prev = resolve_comparison(cur, "previous_equivalent")
    assert prev.end == date(2026, 10, 2) and prev.days == 30


def test_custom_range_clipped_to_as_of_and_flagged_incomplete():
    cur = resolve_period("custom", date(2026, 11, 1), custom_start=date(2026, 10, 20), custom_end=date(2026, 11, 10))
    assert cur.period.end == date(2026, 11, 1) and cur.is_incomplete


def test_invalid_inputs():
    with pytest.raises(PeriodError):
        resolve_period("bogus", date(2026, 1, 1))
    with pytest.raises(PeriodError):
        resolve_period("custom", date(2026, 1, 1))
    with pytest.raises(PeriodError):
        resolve_period("custom", date(2026, 1, 1), custom_start=date(2026, 1, 5), custom_end=date(2026, 1, 1))


def test_weekly_buckets_respect_week_start():
    cur = resolve_period("last_30_days", date(2026, 11, 1))
    b = buckets(cur.period, "weekly", 1)
    assert all(x.isoweekday() == 1 for x in b)
