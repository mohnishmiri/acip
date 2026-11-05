"""Mandatory financial validation of the demonstration scenario (through the API)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

WEEK = "preset=week_to_date&comparison=previous_equivalent"


def test_weekly_totals_are_exact(client):
    r = client.get(f"/api/v1/costs/compare?{WEEK}&group_by=service_category&top_n=4")
    assert r.status_code == 200, r.text
    d = r.json()
    t = d["data"]["totals"]
    assert t["previous"] == 100000.00
    assert t["current"] == 110000.00
    assert t["diff"] == 10000.00
    assert t["pct"] == 10.00
    assert d["meta"]["period"]["start"] == "2026-10-26" and d["meta"]["period"]["end"] == "2026-11-01"
    assert d["meta"]["comparison_period"]["start"] == "2026-10-19" and d["meta"]["comparison_period"]["end"] == "2026-10-25"
    assert d["meta"]["is_demo"] is True


def test_waterfall_identifies_five_contributors_and_reconciles(client):
    d = client.get(f"/api/v1/costs/compare?{WEEK}&group_by=service_category&top_n=4").json()["data"]
    w = d["waterfall"]
    steps = [(s["label"], s["value"]) for s in w["steps"]]
    assert steps == [
        ("Previous period", 100000.0),
        ("Azure Kubernetes Service", 4500.0),
        ("Azure SQL", 2000.0),
        ("Storage", 1500.0),
        ("Networking", 1000.0),
        ("Other (6)", 1000.0),
        ("Current period", 110000.0),
    ]
    assert w["reconciled"] is True and w["reconciliation_difference"] == 0
    running = 100000.0
    for s in w["steps"][1:-1]:
        assert s["start"] == pytest.approx(running)
        running += s["value"]
        assert s["end"] == pytest.approx(running)
    assert running == pytest.approx(110000.0)


def test_service_level_table_matches_scenario(client):
    groups = {g["label"]: g for g in client.get(f"/api/v1/costs/compare?{WEEK}&group_by=service_category").json()["data"]["groups"]}
    expected = {"Azure Kubernetes Service": (30000, 34500), "Azure SQL": (20000, 22000), "Storage": (10000, 11500), "Networking": (8000, 9000)}
    for label, (p, c) in expected.items():
        assert groups[label]["previous"] == p and groups[label]["current"] == c
    other = [g for k, g in groups.items() if k not in expected]
    assert sum(g["previous"] for g in other) == pytest.approx(32000)
    assert sum(g["current"] for g in other) == pytest.approx(33000)


def test_explorer_single_result_is_internally_consistent(client):
    d = client.get(f"/api/v1/costs/explorer?{WEEK}&group_by=service_category&granularity=daily").json()["data"]
    assert sum(g["current"] for g in d["groups"]) == pytest.approx(d["totals"]["current"])
    assert sum(d["series"]["total"]) == pytest.approx(110000.0)
    assert sum(v for v in d["series"]["previous_total"] if v is not None) == pytest.approx(100000.0)
    for i in range(len(d["series"]["buckets"])):
        assert sum(s["values"][i] for s in d["series"]["series"]) == pytest.approx(d["series"]["total"][i])
    assert d["waterfall"]["reconciled"]


def test_overview_kpis_show_week_over_week(client):
    kpis = {k["key"]: k for k in client.get("/api/v1/dashboard/overview").json()["data"]["kpis"]}
    assert kpis["current_week"]["current"] == 110000.0
    assert kpis["current_week"]["previous"] == 100000.0
    assert kpis["current_week"]["pct"] == 10.0
    assert kpis["forecast"]["kind"] == "forecast"  # never presented as actual


def test_drilldown_service_to_resource_to_meter_to_records(client):
    # Azure SQL -> resources
    sql = client.get(f"/api/v1/costs/explorer?{WEEK}&service_category=Azure%20SQL&group_by=resource").json()["data"]
    assert sum(g["current"] for g in sql["groups"]) == pytest.approx(22000)
    assert sum(g["previous"] for g in sql["groups"]) == pytest.approx(20000)
    top = max(sql["groups"], key=lambda g: abs(g["diff"]))
    assert top["label"] == "sqldb-app2-prod-reporting"
    # resource detail + meter-level analysis
    res = client.get(f"/api/v1/resources?{WEEK}&search=sqldb-app2-prod-reporting").json()["data"][0]
    meters = client.get(f"/api/v1/resources/{res['id']}/meters?{WEEK}").json()["data"]
    assert meters["reconciled"] is True
    assert meters["difference"] == pytest.approx(top["diff"])
    assert any(f["type"] == "new_meter" for f in meters["confirmed_facts"])
    assert any(h["type"] == "sku_change" for h in meters["hypotheses"])
    # exact billing records reconcile with the grouped value
    total, page = 0.0, 1
    while True:
        recs = client.get(f"/api/v1/costs/records?{WEEK}&resource={res['resource_id']}&page={page}&page_size=500").json()
        total += sum(r["cost"] for r in recs["data"])
        if page * 500 >= recs["meta"]["total"]:
            break
        page += 1
    assert total == pytest.approx(top["current"], abs=0.01)


def test_aks_increase_is_explained_by_quantity_not_price(client):
    res = client.get(f"/api/v1/resources?{WEEK}&search=aks-userpool-27182818").json()["data"][0]
    m = client.get(f"/api/v1/resources/{res['id']}/meters?{WEEK}").json()["data"]
    eff = {e["key"]: e["value"] for e in m["effects"]}
    assert eff.get("volume", 0) > 0 and abs(eff.get("price", 0)) < 0.01


def test_actual_and_amortized_are_never_mixed(client):
    actual = client.get(f"/api/v1/costs/compare?{WEEK}&cost_type=actual").json()["data"]["totals"]
    amort = client.get(f"/api/v1/costs/compare?{WEEK}&cost_type=amortized").json()["data"]["totals"]
    assert actual["current"] == 110000.0
    # 4 reserved VMs x 9.00/day amortised over 7 days appear only in the amortized dataset
    assert amort["current"] == pytest.approx(110000.0 + 4 * 9.0 * 7)


def test_shared_and_unallocated_are_visible(client):
    groups = {g["key"]: g for g in client.get(f"/api/v1/costs/explorer?{WEEK}&group_by=application").json()["data"]["groups"]}
    assert groups["shared"]["current"] > 0
    assert groups["unallocated"]["current"] > 0
    total = sum(g["current"] for g in groups.values())
    assert total == pytest.approx(110000.0)  # no double counting


def test_expected_anomalies_detected(client):
    rows = client.get("/api/v1/anomalies?page_size=200").json()["data"]
    found = {(a["rule_code"], a["resource_name"] or a["title"]) for a in rows}
    assert ("NEW_EXPENSIVE_RESOURCE", "vm-app2-np-gpu01") in found
    assert any(r == "CONTINUOUS_INCREASE" and n == "stapp1npdata" for r, n in found)
    assert any(r == "DAILY_SERVICE_SPIKE" and "Azure Kubernetes Service in DEMO-App1-Production" in n for r, n in found)
    a = next(x for x in rows if x["rule_code"] == "NEW_EXPENSIVE_RESOURCE")
    detail = client.get(f"/api/v1/anomalies/{a['id']}").json()["data"]
    assert "first appeared in billing" in detail["explanation"]
    assert detail["evidence"]["top_meters"]


def test_anomaly_detection_is_idempotent(client, db):
    from app.models import CostAnomaly
    from app.services.analytics_runner import run_analytics

    # first run absorbs any data ingested by earlier tests; a second run must change nothing
    run_analytics(db, lookback_days=60, notify=False)
    db.commit()
    before = db.query(CostAnomaly).count()
    run_analytics(db, lookback_days=60, notify=False)
    db.commit()
    assert db.query(CostAnomaly).count() == before
    dupes = db.execute(text(
        "SELECT rule_code, scope_key, detection_date FROM cost_anomalies GROUP BY 1, 2, 3, billing_currency HAVING COUNT(*) > 1"
    )).all()
    assert dupes == []


def test_budgets_and_forecasts(client):
    budgets = client.get("/api/v1/budgets").json()["data"]
    assert budgets and all(b["utilization_pct"] is not None for b in budgets)
    fc = client.get("/api/v1/forecasts").json()["data"]
    assert set(fc["methods"]) == {"run_rate", "recent", "trend"}
    assert "not actual" in fc["disclaimer"].lower()
