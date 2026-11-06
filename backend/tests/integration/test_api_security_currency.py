from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

VIEWER = {"X-ACIP-Dev-Role": "viewer"}
LEAD = {"X-ACIP-Dev-Role": "engineering_lead"}


def test_read_allowed_write_forbidden_for_viewer(client):
    assert client.get("/api/v1/costs/explorer", headers=VIEWER).status_code == 200
    body = {"name": "x", "scope_type": "total", "period_type": "monthly", "amount": 10, "start_date": "2026-01-01"}
    r = client.post("/api/v1/budgets", json=body, headers=VIEWER)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.post("/api/v1/ingestion/trigger", json={}, headers=VIEWER).status_code == 403
    assert client.post("/api/v1/azure/connections/test", json={}, headers=VIEWER).status_code == 403


def test_engineering_lead_can_triage_anomalies_but_not_budgets(client):
    aid = client.get("/api/v1/anomalies").json()["data"][0]["id"]
    assert client.post(f"/api/v1/anomalies/{aid}/status", json={"status": "investigating"}, headers=LEAD).status_code == 200
    body = {"name": "x", "scope_type": "total", "period_type": "monthly", "amount": 10, "start_date": "2026-01-01"}
    assert client.post("/api/v1/budgets", json=body, headers=LEAD).status_code == 403


def test_application_scoped_user_sees_only_its_subscriptions(client):
    apps = client.get("/api/v1/admin/applications").json()
    app1 = next(a for a in apps if a["code"] == "app1")["id"]
    h = {"X-ACIP-Dev-Role": "viewer", "X-ACIP-Dev-Application": str(app1)}
    subs = client.get("/api/v1/meta/filters", headers=h).json()["subscriptions"]
    assert {s["subscription_name"] for s in subs} == {"DEMO-App1-Production", "DEMO-App1-NonProduction"}
    groups = client.get("/api/v1/costs/explorer?preset=week_to_date&group_by=subscription", headers=h).json()["data"]["groups"]
    assert {g["label"] for g in groups} <= {"DEMO-App1-Production", "DEMO-App1-NonProduction"}
    other = client.get("/api/v1/resources?preset=week_to_date&search=sqldb-app2-prod-core").json()["data"][0]["id"]
    assert client.get(f"/api/v1/resources/{other}", headers=h).status_code == 404


def test_validation_errors_use_standard_envelope(client):
    r = client.get("/api/v1/costs/explorer?preset=nope")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    r = client.get("/api/v1/costs/explorer?granularity=hourly")
    assert r.status_code == 422


def test_multiple_currencies_are_never_summed(client, demo_db):
    from app.core.db import session_factory
    from app.services.subscription_service import upsert_subscription
    from worker.ingestion.pipeline import sync_subscription

    guid = "e0000000-0000-4000-8000-00000000eeee"
    root: Path = demo_db["root"]
    run = root / "cost-exports" / "eurtest" / "actual" / "acip-actual-daily" / "20261001-20261031" / "run1"
    run.mkdir(parents=True)
    rows = [
        {"date": "10/27/2026", "SubscriptionId": guid, "costInBillingCurrency": "100.00", "billingCurrency": "EUR", "meterCategory": "Storage",
         "ResourceId": f"/subscriptions/{guid}/resourceGroups/rg-eu/providers/Microsoft.Storage/storageAccounts/steu1"},
        {"date": "10/28/2026", "SubscriptionId": guid, "costInBillingCurrency": "50.00", "billingCurrency": "EUR", "meterCategory": "Storage",
         "ResourceId": f"/subscriptions/{guid}/resourceGroups/rg-eu/providers/Microsoft.Storage/storageAccounts/steu1"},
    ]
    with open(run / "part_0_0001.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (run / "manifest.json").write_text(json.dumps({"runInfo": {"submittedTime": "2026-11-02T06:00:00Z", "startDate": "2026-10-01T00:00:00", "endDate": "2026-10-31T00:00:00"}}))
    sf = session_factory()
    with sf() as db:
        sub = upsert_subscription(db, {"subscription_id": guid, "subscription_name": "EUR-Test", "environment": "unallocated", "billing_currency": "EUR",
                                       "exports": [{"dataset_type": "actual", "export_name": "acip-actual-daily", "container": "cost-exports",
                                                    "root_folder_path": "eurtest/actual", "storage_account_url": "local://test"}]})
        db.commit()
        sid = sub.id
    sync_subscription(sf, sid)

    usd = client.get("/api/v1/costs/compare?preset=week_to_date").json()
    assert usd["data"]["totals"]["current"] == 110000.0  # EUR excluded from the USD total
    assert usd["meta"]["currency"] == "USD"
    assert any("EUR" in w for w in usd["meta"]["warnings"])
    eur = client.get("/api/v1/costs/compare?preset=week_to_date&currency=EUR").json()
    assert eur["data"]["totals"]["current"] == 150.0 and eur["meta"]["currency"] == "EUR"


def test_saved_comparisons_roundtrip(client):
    r = client.post("/api/v1/costs/saved-comparisons", json={"name": "Weekly AKS", "params": {"preset": "week_to_date", "service_category": ["Azure Kubernetes Service"]}})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert any(c["id"] == cid for c in client.get("/api/v1/costs/saved-comparisons").json())
    assert client.delete(f"/api/v1/costs/saved-comparisons/{cid}").status_code == 204


def test_application_delete_refused_while_referenced(client):
    app1 = next(a for a in client.get("/api/v1/admin/applications").json() if a["code"] == "app1")
    r = client.delete(f"/api/v1/admin/applications/{app1['id']}")
    assert r.status_code == 409
    new = client.post("/api/v1/admin/applications", json={"code": "tmp-app", "name": "Temp"}).json()["id"]
    assert client.delete(f"/api/v1/admin/applications/{new}").status_code == 204


def test_monthly_series_flags_partial_buckets(client):
    s = client.get("/api/v1/costs/explorer?preset=last_90_days&granularity=monthly").json()["data"]["series"]
    cov = s["coverage"]
    assert len(cov) == len(s["buckets"])
    assert cov[-1][0] < cov[-1][1]  # Nov 2026 has 1 of 30 days in the period


def test_application_codes_may_be_upper_case(client):
    new = client.post("/api/v1/admin/applications", json={"code": "ATTCC-TEST", "name": "Upper case code"})
    assert new.status_code == 201, new.text
    aid = new.json()["id"]
    assert client.put(f"/api/v1/admin/applications/{aid}", json={"code": "ATTCC-TEST", "name": "Renamed"}).status_code == 200
    assert client.delete(f"/api/v1/admin/applications/{aid}").status_code == 204
