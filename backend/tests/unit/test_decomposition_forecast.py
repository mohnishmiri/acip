from datetime import date, timedelta
from decimal import Decimal as D

from app.analytics.decomposition import MeterRow, decompose
from app.forecasting.forecast import budget_status, forecast_period


def row(rk, meter, pc, cc, pq, cq, prec=1, crec=1, charge="Usage", pm="OnDemand", cat="Virtual Machines"):
    return MeterRow(rk, rk, meter, cat, "sub", meter, "1 Hour", charge, pm, None, D(str(pc)), D(str(cc)), D(str(pq)), D(str(cq)), prec, crec)


def test_volume_and_price_split_sums_exactly():
    # 500 h @ 4.00 -> 650 h @ 4.00 : pure volume
    r = decompose([row("r1", "compute", 2000, 2600, 500, 650)])
    eff = {e["key"]: e["value"] for e in r["effects"]}
    assert eff == {"volume": 600.0}
    # 100 GB @ 1.0 -> 100 GB @ 1.2 : pure price
    r = decompose([row("r2", "storage", 100, 120, 100, 100)])
    assert {e["key"]: e["value"] for e in r["effects"]} == {"price": 20.0}
    # mixed
    r = decompose([row("r3", "net", 300, 525, 200, 350)])
    assert r["reconciled"]
    assert sum(e["value"] for e in r["effects"]) == 225.0


def test_new_and_removed_meters_and_resources():
    rows = [
        row("r1", "gp", 120, 20, 240, 40),
        row("r1", "bc", 0, 300, 0, 220, prec=0, crec=6),
        row("r2", "gpu", 0, 290, 0, 96, prec=0, crec=4),  # new resource
        row("r3", "old", 50, 0, 10, 0, prec=3, crec=0),  # removed resource
        row("r1", "fee", 10, -150, 0, 0, charge="Refund"),
    ]
    r = decompose(rows)
    eff = {e["key"]: e["value"] for e in r["effects"]}
    assert eff["new_meter"] == 300.0
    assert eff["new_resource"] == 290.0
    assert eff["removed_resource"] == -50.0
    assert eff["credits_refunds"] == -160.0
    assert r["reconciled"]
    assert any(f["type"] == "meter_swap" for f in r["confirmed_facts"])
    assert any(h["type"] == "sku_change" for h in r["hypotheses"])


def test_hypotheses_are_never_presented_as_facts():
    r = decompose([row("r1", "compute", 2000, 2600, 500, 650)])
    assert all("cannot confirm" in h["text"] or "Not verifiable" in h["text"] or "Verify" in h["text"] or "verify" in h["text"] for h in r["hypotheses"])


def _series(start: date, days: int, value) -> dict:
    return {start + timedelta(days=i): D(str(value(i))) for i in range(days)}


def test_run_rate_forecast():
    daily = _series(date(2026, 11, 1), 10, lambda i: 100)
    fc = forecast_period(daily, as_of=date(2026, 11, 10), period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), method="run_rate")
    assert fc.actual_to_date == D(1000) and fc.forecast_total == D(3000) and fc.remaining_days == 20


def test_recent_forecast_uses_last_7_days():
    daily = _series(date(2026, 10, 25), 17, lambda i: 100 if i < 10 else 200)
    fc = forecast_period(daily, as_of=date(2026, 11, 10), period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), method="recent")
    assert fc.daily_rate == D(200)


def test_trend_forecast_projects_growth_and_falls_back_without_history():
    daily = _series(date(2026, 9, 12), 60, lambda i: 100 + i)
    fc = forecast_period(daily, as_of=date(2026, 11, 10), period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), method="trend")
    assert fc.projection[0][1] > D(155)
    short = _series(date(2026, 11, 5), 6, lambda i: 100)
    fc2 = forecast_period(short, as_of=date(2026, 11, 10), period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), method="trend")
    assert fc2.notes


def test_budget_status_handles_zero_budget():
    s = budget_status(D(0), D(10), D(20))
    assert s["utilization_pct"] is None and s["forecast_utilization_pct"] is None
    s = budget_status(D(1000), D(800), D(1100))
    assert s["utilization_pct"] == D(80) and s["remaining"] == D(200) and s["forecast_variance"] == D(100)
