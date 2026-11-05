from datetime import date, timedelta
from decimal import Decimal as D

from app.anomaly_detection.rules import (
    classify_severity,
    detect_continuous_increase,
    detect_daily_spike,
    detect_monthly_spike,
    detect_weekly_spike,
)

T = date(2026, 10, 28)


def flat(value, days=60, end=T):
    return {end - timedelta(days=i): D(str(value)) for i in range(days)}


def test_daily_spike_requires_both_relative_and_absolute_significance():
    s = flat(1000)
    s[T] = D(1600)  # +600 (+60%)
    det = detect_daily_spike(s, T, pct_threshold=25, min_abs=200)
    assert det is not None and det.abs_increase == D(600) and det.pct_increase == D(60)
    tiny = flat(2)
    tiny[T] = D(12)  # +500% but only $10
    assert detect_daily_spike(tiny, T, pct_threshold=25, min_abs=200) is None
    small_pct = flat(100000)
    small_pct[T] = D(101000)  # +$1,000 but +1%
    assert detect_daily_spike(small_pct, T, pct_threshold=25, min_abs=200) is None


def test_equivalent_weekday_baseline_ignores_normal_weekend_dips():
    s = {}
    for i in range(60):
        d = T - timedelta(days=i)
        s[d] = D(200) if d.isoweekday() >= 6 else D(1000)
    sunday = next(T - timedelta(days=i) for i in range(7) if (T - timedelta(days=i)).isoweekday() == 7)
    assert detect_daily_spike(s, sunday, method="same_weekday_median") is None
    monday = sunday + timedelta(days=1)
    assert detect_daily_spike(s, monday, method="rolling_median", window=7, pct_threshold=25, min_abs=200) is None


def test_insufficient_history_does_not_alert():
    s = flat(100, days=5)
    s[T] = D(10000)
    assert detect_daily_spike(s, T, min_history_days=14) is None


def test_weekly_and_monthly_spikes():
    s = flat(1000, days=90)
    for i in range(7):
        s[T - timedelta(days=i)] = D(1300)
    assert detect_weekly_spike(s, T, pct_threshold=15, min_abs=750) is not None
    m = flat(1000, days=90, end=date(2026, 10, 10))
    for i in range(10):
        m[date(2026, 10, 1) + timedelta(days=i)] = D(1500)
    det = detect_monthly_spike(m, date(2026, 10, 10), pct_threshold=15, min_abs=2000)
    assert det is not None and det.abs_increase == D(5000)


def test_continuous_increase():
    s = {}
    for w in range(6):
        for i in range(7):
            s[T - timedelta(days=7 * w + i)] = D(100) * (D("1.1") ** (5 - w))
    assert detect_continuous_increase(s, T, weeks=4, min_step_pct=5, min_abs=50) is not None
    assert detect_continuous_increase(flat(100), T, weeks=4, min_step_pct=5, min_abs=50) is None


def test_severity_bands_and_sensitivity():
    assert classify_severity(D(6000), D(60)) == "critical"
    assert classify_severity(D(6000), D(15)) == "low"  # large $ but small % -> lower band
    assert classify_severity(D(50), D(400)) == "informational"
    assert classify_severity(D(450), D(25), sensitivity="high") == "medium"
    assert classify_severity(D(2500), None) == "high"  # new spend: absolute bands only
