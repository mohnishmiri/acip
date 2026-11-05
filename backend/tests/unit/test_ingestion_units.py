from datetime import date
from decimal import Decimal as D

import pytest

from app.analytics.allocation import DEFAULT_CATEGORY_RULES, AllocationEngine, _Rule
from worker.export_processing.normalizer import RowError, RunContext, normalise_row, parse_date, parse_tags, resource_type_from_id
from worker.export_processing.schema import build_mapping

SUB = "11111111-2222-3333-4444-555555555555"
CTX = RunContext(subscription_fk=1, subscription_guid=SUB, dataset_type="actual", default_currency="USD", export_run_id=1, ingestion_file_id=1, is_demo=False)


def test_schema_detection_modern_legacy_focus():
    assert build_mapping(["date", "costInBillingCurrency", "SubscriptionId"], "actual").detected_schema == "modern_actual_amortized"
    assert build_mapping(["UsageDateTime", "PreTaxCost", "Date"], "actual").detected_schema == "legacy_pretax"
    focus = build_mapping(["ChargePeriodStart", "BilledCost", "EffectiveCost", "SubAccountId"], "amortized")
    assert focus.detected_schema == "focus" and focus.field_to_column["cost"] == "EffectiveCost"
    assert build_mapping(["ChargePeriodStart", "BilledCost", "EffectiveCost"], "actual").field_to_column["cost"] == "BilledCost"


def test_missing_required_columns_reported():
    m = build_mapping(["foo", "bar"], "actual")
    assert set(m.missing_required) == {"usage_date", "cost"}


def test_unmapped_columns_preserved():
    m = build_mapping(["Date", "CostInBillingCurrency", "SomeNewColumn"], "actual")
    row = normalise_row({"Date": "2026-10-01", "CostInBillingCurrency": "1.5", "SomeNewColumn": "x"}, m, CTX, 2)
    assert row["extra"] == {"SomeNewColumn": "x"}


def test_dates_and_tags():
    assert parse_date("10/05/2026") == date(2026, 10, 5)  # MM/DD/YYYY
    assert parse_date("2026-10-05") == date(2026, 10, 5)
    assert parse_tags('"env": "prod","owner": "a@b"') == {"env": "prod", "owner": "a@b"}
    assert parse_tags('{"env":"prod"}') == {"env": "prod"}
    with pytest.raises(RowError):
        parse_date("not a date")


def test_resource_parsing_and_subscription_guard():
    rid = f"/subscriptions/{SUB}/resourceGroups/RG-Data/providers/Microsoft.Sql/servers/s1/databases/db1"
    assert resource_type_from_id(rid) == "microsoft.sql/servers/databases"
    m = build_mapping(["date", "costInBillingCurrency", "SubscriptionId", "ResourceId", "billingCurrency"], "actual")
    row = normalise_row({"date": "10/01/2026", "costInBillingCurrency": "12.3456789", "SubscriptionId": SUB, "ResourceId": rid, "billingCurrency": "eur"}, m, CTX, 2)
    assert row["resource_key"] == rid.lower() and row["resource_group"] == "rg-data" and row["resource_name"] == "db1"
    assert row["cost"] == D("12.3456789") and row["billing_currency"] == "EUR"
    with pytest.raises(RowError) as e:
        normalise_row({"date": "10/01/2026", "costInBillingCurrency": "1", "SubscriptionId": "99999999-2222-3333-4444-555555555555"}, m, CTX, 3)
    assert e.value.error_type == "subscription_mismatch"


def _engine(precedence=None, app_maps=None, tag_maps=None):
    rules = [_Rule(i, f, p.lower(), c, prio) for i, (prio, f, p, c) in enumerate(DEFAULT_CATEGORY_RULES)]
    return AllocationEngine(
        subscriptions={1: (10, 100), 2: (None, None)},
        environments={"production": 100, "non_production": 101, "shared": 102, "unallocated": 103, "development": 104},
        environment_groups={100: "production", 101: "non_production", 102: "shared", 103: "unallocated", 104: "non_production"},
        applications={"app1": 10, "app2": 20},
        app_mappings=app_maps or [],
        tag_mappings=tag_maps or [{"id": 1, "tag_key": "environment", "tag_value": None, "target_dimension": "environment", "target_value": None, "priority": 1},
                                  {"id": 2, "tag_key": "owner", "tag_value": None, "target_dimension": "owner", "target_value": None, "priority": 1}],
        category_rules=rules,
        precedence=precedence or ["resource_group_rule", "subscription", "resource_tag"],
    )


def test_subscription_mapping_is_primary():
    a = _engine().allocate({"subscription_fk": 1, "resource_group": "rg", "tags": {"environment": "dev", "Owner": "x@y"}})
    assert (a.application_id, a.environment_id, a.allocation_status, a.owner) == (10, 100, "allocated", "x@y")


def test_untagged_resource_in_unmapped_subscription_is_unallocated_not_production():
    a = _engine().allocate({"subscription_fk": 2, "resource_group": "rg"})
    assert a.application_id is None and a.environment_id == 103 and a.allocation_status == "unallocated"


def test_resource_group_rule_marks_shared_once():
    maps = [{"id": 1, "match_type": "resource_group", "pattern": "rg-hub-*", "subscription_fk": None, "application_id": None,
             "environment_id": 102, "allocation_status": "shared", "priority": 1}]
    a = _engine(app_maps=maps).allocate({"subscription_fk": 1, "resource_group": "rg-hub-network"})
    assert a.application_id is None and a.environment_id == 102 and a.allocation_status == "shared"


def test_tag_precedence_configurable():
    row = {"subscription_fk": 1, "tags": {"environment": "dev"}}
    assert _engine().allocate(row).environment_id == 100  # default: subscription wins
    tagged_first = _engine(precedence=["resource_tag", "subscription"]).allocate(row)
    assert tagged_first.environment_id == 104 and tagged_first.application_id == 10  # env from tag, app from subscription


def test_service_categories():
    e = _engine()
    assert e.categorize({"resource_group": "mc_rg_aks_cluster_eastus", "meter_category": "Virtual Machines"}) == "Azure Kubernetes Service"
    assert e.categorize({"meter_category": "Bandwidth"}) == "Networking"
    assert e.categorize({"meter_category": "Log Analytics"}) == "Azure Monitor"
    assert e.categorize({"meter_category": "Something New"}) == "Other Services"


def test_missing_subscriptions_config_file_is_not_fatal(monkeypatch):
    from app.core.config import get_settings
    from app.services.subscription_service import load_config_file

    monkeypatch.setenv("AZURE_SUBSCRIPTIONS_CONFIG", "/config/does-not-exist.json")
    get_settings.cache_clear()
    try:
        assert load_config_file(None)["skipped"] == 1  # db never touched
    finally:
        get_settings.cache_clear()
