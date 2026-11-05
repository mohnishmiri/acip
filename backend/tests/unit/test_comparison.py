from decimal import Decimal as D

from app.analytics.comparison import ComparedItem, build_waterfall, classify_change, compute_metrics, compute_totals, pct_change, sort_items


def items(*rows):
    return [ComparedItem(key=k, label=k, previous=D(str(p)), current=D(str(c))) for k, p, c in rows]


SCENARIO = [
    ("AKS", 30000, 34500),
    ("SQL", 20000, 22000),
    ("Storage", 10000, 11500),
    ("Network", 8000, 9000),
    ("VMs", 12000, 12300),
    ("AppService", 8000, 8250),
    ("Monitor", 7000, 7350),
    ("KeyVault", 1500, 1520),
    ("ACR", 2000, 2030),
    ("OtherSvc", 1500, 1550),
]


def test_scenario_totals_and_percentage():
    its = items(*SCENARIO)
    tp, tc, diff = compute_metrics(its)
    assert (tp, tc, diff) == (D(100000), D(110000), D(10000))
    assert pct_change(tp, tc) == D(10)


def test_scenario_waterfall_five_contributors_reconciles():
    its = items(*SCENARIO)
    tp, tc, _ = compute_metrics(its)
    w = build_waterfall(its, tp, tc, top_n=4)
    labels = [(s.label, s.value) for s in w.steps]
    assert labels == [
        ("Previous period", D(100000)),
        ("AKS", D(4500)),
        ("SQL", D(2000)),
        ("Storage", D(1500)),
        ("Network", D(1000)),
        ("Other (6)", D(1000)),
        ("Current period", D(110000)),
    ]
    assert w.reconciled and w.reconciliation_difference == 0
    assert w.steps[-2].end == D(110000)


def test_waterfall_with_negative_contributions_reconciles():
    its = items(("a", 100, 50), ("b", 10, 80), ("c", 5, 0), ("d", 0, 3))
    tp, tc, _ = compute_metrics(its)
    w = build_waterfall(its, tp, tc, top_n=2)
    assert w.reconciled
    assert [s.kind for s in w.steps] == ["start", "increase", "decrease", "other", "end"]
    assert sum((s.value for s in w.steps[1:-1]), D(0)) == tc - tp


def test_zero_previous_never_divides_by_zero():
    assert pct_change(D(0), D(100)) is None
    assert pct_change(D(0), D(0)) is None
    t = compute_totals(D(0), D(50), current_days=7, previous_days=7)
    assert t.pct is None and t.status == "new"


def test_current_zero_is_removed():
    assert classify_change(D(100), D(0)) == "removed"


def test_negative_previous_keeps_direction():
    # net credit last period (-100) to +50 now: an increase of 150 = +150%
    assert pct_change(D(-100), D(50)) == D(150)


def test_new_vs_increase_uses_record_presence():
    assert classify_change(D(0), D(10), previous_records=0, current_records=3) == "new"
    # had records but zero cost (free tier) -> increase, not new
    assert classify_change(D(0), D(10), previous_records=5, current_records=5) == "increased"
    assert classify_change(D(10), D(0), previous_records=5, current_records=0) == "removed"


def test_default_ranking_is_absolute_not_percentage():
    its = items(("tiny", 2, 12), ("big", 50000, 60000))  # +500% vs +20%
    compute_metrics(its)
    assert [i.key for i in sort_items(its, "abs_diff")] == ["big", "tiny"]
    assert [i.key for i in sort_items(its, "pct_increase")] == ["tiny", "big"]


def test_percentage_sort_places_new_items_last():
    its = [ComparedItem("new", "new", D(0), D(500), 0, 4), ComparedItem("up", "up", D(100), D(150), 3, 3)]
    compute_metrics(its)
    assert [i.key for i in sort_items(its, "pct_increase")] == ["up", "new"]


def test_contribution_and_share():
    its = items(*SCENARIO)
    compute_metrics(its)
    aks = next(i for i in its if i.key == "AKS")
    assert aks.contribution_pct == D(45)
    assert round(aks.share_of_total, 4) == round(D(34500) / D(110000) * 100, 4)


def test_run_rate_for_incomplete_period():
    t = compute_totals(D(700), D(300), current_days=3, previous_days=3, nominal_days=7)
    assert t.run_rate == D(700)
