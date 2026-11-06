"""Idempotent reference data: environments, roles, default rules and settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.allocation import CATEGORY_RULES_VERSION, DEFAULT_CATEGORY_RULES, DEFAULT_TAG_MAPPINGS
from app.models import AlertRule, AnomalyRule, ApplicationSetting, Environment, ResourceTagMapping, Role, ServiceCategoryRule

ENVIRONMENTS = [
    # code, name, group, is_production, sort
    ("production", "Production", "production", True, 10),
    ("non_production", "Non-Production", "non_production", False, 20),
    ("development", "Development", "non_production", False, 30),
    ("testing", "Testing", "non_production", False, 40),
    ("uat", "UAT", "non_production", False, 50),
    ("shared", "Shared Services", "shared", False, 60),
    ("unallocated", "Unallocated", "unallocated", False, 70),
]

ROLES = [
    ("administrator", "Administrator", "Full access including subscriptions, connections, ingestion and settings.", "ACIP.Administrator"),
    ("finops_analyst", "FinOps Analyst", "All reports; manage budgets, anomaly status, savings status and alert rules.", "ACIP.FinOpsAnalyst"),
    ("engineering_lead", "Engineering Lead", "All reports; update anomaly and savings investigation status.", "ACIP.EngineeringLead"),
    ("viewer", "Read-only Viewer", "Read-only access to reports.", "ACIP.Viewer"),
]

ANOMALY_RULES = [
    {
        "code": "DAILY_SERVICE_SPIKE",
        "name": "Daily service cost spike",
        "description": "Daily cost of an Azure service in a subscription compared with the median of the same weekday over the previous 4 weeks.",
        "detection_type": "daily_spike",
        "scope_level": "subscription_service",
        "filters": {},
        "params": {
            "method": "same_weekday_median", "window": 4, "pct_threshold": 25, "min_abs": 250, "min_history_days": 21,
            "category_overrides": {
                "Networking": {"pct_threshold": 20, "min_abs": 100},
                "Storage": {"pct_threshold": 15, "min_abs": 100},
                "Azure Monitor": {"pct_threshold": 25, "min_abs": 100},
                "Azure SQL": {"pct_threshold": 20, "min_abs": 150},
                "Virtual Machines": {"pct_threshold": 20, "min_abs": 150},
            },
        },
    },
    {
        "code": "DAILY_RESOURCE_SPIKE",
        "name": "Daily resource cost spike",
        "description": "Daily cost of a resource compared with the median of its previous 14 days.",
        "detection_type": "daily_spike",
        "scope_level": "resource",
        "filters": {},
        "params": {"method": "rolling_median", "window": 14, "pct_threshold": 40, "min_abs": 150, "min_history_days": 14},
    },
    {
        "code": "WEEKLY_SERVICE_SPIKE",
        "name": "Weekly service cost increase",
        "description": "Last 7 days of a service in a subscription compared with the average of the previous 4 weeks.",
        "detection_type": "weekly_spike",
        "scope_level": "subscription_service",
        "filters": {},
        "params": {"weeks": 4, "pct_threshold": 12, "min_abs": 750},
    },
    {
        "code": "MONTHLY_APPLICATION_SPIKE",
        "name": "Monthly application cost increase",
        "description": "Month-to-date cost of an application environment compared with the same elapsed days of the previous month.",
        "detection_type": "monthly_spike",
        "scope_level": "application_environment",
        "filters": {},
        "params": {"pct_threshold": 12, "min_abs": 3000, "min_elapsed_days": 7},
    },
    {
        "code": "NEW_EXPENSIVE_RESOURCE",
        "name": "New expensive resource",
        "description": "Resource that first appeared in billing within the last 7 days with an average daily cost above the threshold.",
        "detection_type": "new_resource",
        "scope_level": "resource",
        "filters": {},
        "params": {"lookback_days": 7, "min_daily_cost": 40},
    },
    {
        "code": "NON_PROD_DAILY_SPIKE",
        "name": "Unexpected Non-Production expenditure",
        "description": "Daily cost of a Non-Production application environment compared with the median of the same weekday over 4 weeks.",
        "detection_type": "daily_spike",
        "scope_level": "application_environment",
        "filters": {"environment_groups": ["non_production"]},
        "params": {"method": "same_weekday_median", "window": 4, "pct_threshold": 15, "min_abs": 60, "min_history_days": 21},
    },
    {
        "code": "CONTINUOUS_INCREASE",
        "name": "Continuous cost increase",
        "description": "Resource whose weekly cost increased in each of the last 4 weeks (each step at least 3%).",
        "detection_type": "continuous_increase",
        "scope_level": "resource",
        "filters": {},
        "params": {"weeks": 4, "min_step_pct": 3, "min_abs": 100},
    },
]

ALERT_RULES = [
    {"name": "Cost anomalies (medium and above)", "alert_type": "anomaly", "min_severity": "medium"},
    {"name": "Budget thresholds", "alert_type": "budget_threshold", "min_severity": None},
    {"name": "Forecast exceeds budget", "alert_type": "budget_forecast", "min_severity": None},
    {"name": "Ingestion failures", "alert_type": "ingestion_failure", "min_severity": None},
    {"name": "Delayed subscription data", "alert_type": "data_delay", "min_severity": None},
    {"name": "New savings opportunities (> 500/month)", "alert_type": "savings_opportunity", "min_severity": None, "params": {"min_monthly_savings": 500}},
]


CATEGORY_RULES_VERSION_KEY = "seed.category_rules_version"
V1_CATEGORY_PRIORITIES = 99  # rules with priority <= 99 shipped in v1


def _seed_category_rules(db: Session) -> int:
    """Install default category rules; on upgrade add only rules introduced after the stored
    version (rules an administrator deleted earlier are not re-created)."""
    row = db.get(ApplicationSetting, CATEGORY_RULES_VERSION_KEY)
    existing = {(r.match_field, r.pattern.lower()) for r in db.execute(select(ServiceCategoryRule)).scalars()}
    if not existing:
        candidates = DEFAULT_CATEGORY_RULES
    elif row is None or int(row.value) < CATEGORY_RULES_VERSION:
        candidates = [r for r in DEFAULT_CATEGORY_RULES if r[0] > V1_CATEGORY_PRIORITIES]  # v2 additions
    else:
        candidates = []
    added = 0
    for prio, field, pattern, category in candidates:
        if (field, pattern.lower()) not in existing:
            db.add(ServiceCategoryRule(match_field=field, pattern=pattern, category=category, priority=prio, description="Default rule"))
            added += 1
    if row is None:
        db.add(ApplicationSetting(key=CATEGORY_RULES_VERSION_KEY, value=CATEGORY_RULES_VERSION, description="Internal: default category rule set version", updated_by="seed"))
    elif int(row.value) < CATEGORY_RULES_VERSION:
        row.value = CATEGORY_RULES_VERSION
    return added


def seed_reference_data(db: Session) -> dict[str, int]:
    counts = {"environments": 0, "roles": 0, "category_rules": 0, "tag_mappings": 0, "anomaly_rules": 0, "alert_rules": 0}
    existing_envs = {e.code for e in db.execute(select(Environment)).scalars()}
    for code, name, group, is_prod, sort in ENVIRONMENTS:
        if code not in existing_envs:
            db.add(Environment(code=code, name=name, environment_group=group, is_production=is_prod, sort_order=sort))
            counts["environments"] += 1
    existing_roles = {r.code for r in db.execute(select(Role)).scalars()}
    for code, name, desc, app_role in ROLES:
        if code not in existing_roles:
            db.add(Role(code=code, name=name, description=desc, entra_app_role=app_role))
            counts["roles"] += 1
    counts["category_rules"] = _seed_category_rules(db)
    if not db.execute(select(ResourceTagMapping).limit(1)).first():
        for key, dim, prio in DEFAULT_TAG_MAPPINGS:
            db.add(ResourceTagMapping(tag_key=key, target_dimension=dim, priority=prio, description="Default mapping"))
            counts["tag_mappings"] += 1
    existing_rules = {r.code for r in db.execute(select(AnomalyRule)).scalars()}
    for r in ANOMALY_RULES:
        if r["code"] not in existing_rules:
            db.add(AnomalyRule(**r))
            counts["anomaly_rules"] += 1
    if not db.execute(select(AlertRule).limit(1)).first():
        for a in ALERT_RULES:
            db.add(AlertRule(name=a["name"], alert_type=a["alert_type"], min_severity=a.get("min_severity"), params=a.get("params", {}), filters={}, channels=["in_app"]))
            counts["alert_rules"] += 1
    db.flush()
    return counts
