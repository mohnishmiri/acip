"""Cost allocation engine.

Assigns each billing row exactly once to:
  * an application / environment / allocation status (allocated | shared | unallocated)
  * a reporting service category
  * owner / cost center / project / team / business unit / workload (from tags)

Primary classification is the subscription -> application mapping. Resource-group rules
(admin-defined, e.g. a hub network RG marked as Shared Services) and resource tags can
override according to the configurable precedence. When nothing matches, the row is
reported as Unallocated -- untagged resources are never silently assigned to Production.
Each row is assigned to exactly one bucket, so shared charges are never double counted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    ApplicationMapping,
    AzureSubscription,
    Environment,
    ResourceTagMapping,
    ServiceCategoryRule,
)

DEFAULT_CATEGORY = "Other Services"

SERVICE_CATEGORIES = [
    "Azure Kubernetes Service",
    "Virtual Machines",
    "Azure SQL",
    "Storage",
    "Networking",
    "Azure Monitor",
    "App Service",
    "Key Vault",
    "Container Registry",
    "Azure Synapse Analytics",
    "Azure Databricks",
    "Azure Data Factory",
    "Messaging & Integration",
    "Other Databases",
    DEFAULT_CATEGORY,
]

ENV_ALIASES: dict[str, list[str]] = {
    "production": ["prod", "production", "prd", "live"],
    "non_production": ["nonprod", "non-prod", "non_prod", "non-production", "non_production", "nonproduction", "np"],
    "development": ["dev", "development", "develop"],
    "testing": ["test", "testing", "qa", "sit"],
    "uat": ["uat", "staging", "stage", "preprod", "pre-prod"],
    "shared": ["shared", "shared-services", "shared_services", "sharedservices", "hub", "platform"],
}

ATTRIBUTE_DIMENSIONS = ["owner", "cost_center", "project", "team", "business_unit", "workload"]
TARGET_DIMENSIONS = ["application", "environment", *ATTRIBUTE_DIMENSIONS]

CATEGORY_MATCH_FIELDS = [
    "resource_group",
    "resource_type",
    "meter_category",
    "meter_subcategory",
    "meter_name",
    "service_name",
    "consumed_service",
]


@dataclass(frozen=True)
class Allocation:
    application_id: int | None
    environment_id: int | None
    allocation_status: str
    service_category: str
    owner: str | None
    cost_center: str | None
    project: str | None
    team: str | None
    business_unit: str | None
    workload: str | None
    source: str


@dataclass
class _Rule:
    id: int
    match_field: str
    pattern: str
    category: str
    priority: int


class AllocationEngine:
    def __init__(
        self,
        *,
        subscriptions: dict[int, tuple[int | None, int | None]],
        environments: dict[str, int],
        environment_groups: dict[int, str],
        applications: dict[str, int],
        app_mappings: list[dict[str, Any]],
        tag_mappings: list[dict[str, Any]],
        category_rules: list[_Rule],
        precedence: list[str],
    ):
        self.subscriptions = subscriptions
        self.environments = environments
        self.environment_groups = environment_groups
        self.applications = applications
        self.app_mappings = sorted(app_mappings, key=lambda m: (m["priority"], m["id"]))
        self.tag_mappings = sorted(tag_mappings, key=lambda m: (m["priority"], m["id"]))
        self.category_rules = sorted(category_rules, key=lambda r: (r.priority, r.id))
        self.precedence = precedence or ["resource_group_rule", "subscription", "resource_tag"]
        self._alias_to_env: dict[str, str] = {}
        for code, aliases in ENV_ALIASES.items():
            for a in aliases:
                self._alias_to_env[a] = code
        self._cache: dict[tuple, Allocation] = {}

    # -------------------------------------------------------------------------------
    @classmethod
    def load(cls, db: Session, precedence: list[str] | None = None) -> AllocationEngine:
        from app.services.settings_service import get_setting

        subs = {s.id: (s.application_id, s.environment_id) for s in db.execute(select(AzureSubscription)).scalars()}
        envs = list(db.execute(select(Environment)).scalars())
        apps: dict[str, int] = {}
        for a in db.execute(select(Application)).scalars():
            apps[a.code.lower()] = a.id
            apps[a.name.lower()] = a.id
        app_maps = [
            {
                "id": m.id,
                "match_type": m.match_type,
                "pattern": m.pattern.lower(),
                "subscription_fk": m.subscription_fk,
                "application_id": m.application_id,
                "environment_id": m.environment_id,
                "allocation_status": m.allocation_status,
                "priority": m.priority,
            }
            for m in db.execute(select(ApplicationMapping).where(ApplicationMapping.enabled.is_(True))).scalars()
        ]
        tag_maps = [
            {
                "id": t.id,
                "tag_key": t.tag_key.lower(),
                "tag_value": t.tag_value.lower() if t.tag_value else None,
                "target_dimension": t.target_dimension,
                "target_value": t.target_value,
                "priority": t.priority,
            }
            for t in db.execute(select(ResourceTagMapping).where(ResourceTagMapping.enabled.is_(True))).scalars()
        ]
        rules = [
            _Rule(r.id, r.match_field, r.pattern.lower(), r.category, r.priority)
            for r in db.execute(select(ServiceCategoryRule).where(ServiceCategoryRule.enabled.is_(True))).scalars()
        ]
        return cls(
            subscriptions=subs,
            environments={e.code: e.id for e in envs},
            environment_groups={e.id: e.environment_group for e in envs},
            applications=apps,
            app_mappings=app_maps,
            tag_mappings=tag_maps,
            category_rules=rules,
            precedence=precedence or get_setting(db, "attribution.precedence"),
        )

    # -------------------------------------------------------------------------------
    def categorize(self, row: dict[str, Any]) -> str:
        for rule in self.category_rules:
            value = row.get(rule.match_field)
            if value and fnmatchcase(str(value).lower(), rule.pattern):
                return rule.category
        return DEFAULT_CATEGORY

    def _env_code_from_value(self, value: str) -> str | None:
        v = value.strip().lower()
        if v in self.environments:
            return v
        return self._alias_to_env.get(v)

    def _tag_values(self, tags: dict[str, Any] | None) -> dict[str, str | None]:
        """Resolve all tag-mapped dimensions (first matching mapping by priority wins)."""
        out: dict[str, str | None] = {}
        if not tags:
            return out
        lower = {str(k).lower(): ("" if v is None else str(v)) for k, v in tags.items()}
        for m in self.tag_mappings:
            dim = m["target_dimension"]
            if dim in out:
                continue
            if m["tag_key"] not in lower:
                continue
            val = lower[m["tag_key"]]
            if m["tag_value"] is not None and val.lower() != m["tag_value"]:
                continue
            resolved = m["target_value"] if m["target_value"] is not None else val
            if resolved:
                out[dim] = resolved
        return out

    def allocate(self, row: dict[str, Any]) -> Allocation:
        tags = row.get("tags") or None
        key = (
            row.get("subscription_fk"),
            row.get("resource_group"),
            row.get("resource_key"),
            row.get("resource_type"),
            row.get("meter_category"),
            row.get("meter_subcategory"),
            row.get("meter_name"),
            row.get("service_name"),
            row.get("consumed_service"),
            row.get("cost_center_column"),
            json.dumps(tags, sort_keys=True) if tags else None,
        )
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        result = self._allocate(row, tags)
        if len(self._cache) < 200_000:
            self._cache[key] = result
        return result

    def _allocate(self, row: dict[str, Any], tags: dict[str, Any] | None) -> Allocation:
        sub_fk = row.get("subscription_fk")
        tag_vals = self._tag_values(tags)
        app_id: int | None = None
        env_id: int | None = None
        status: str | None = None
        src_app = src_env = "none"
        rg = (row.get("resource_group") or "").lower()
        rkey = (row.get("resource_key") or "").lower()

        for source in self.precedence:
            if app_id is not None and env_id is not None:
                break
            if source == "resource_group_rule":
                for m in self.app_mappings:
                    if m["subscription_fk"] and m["subscription_fk"] != sub_fk:
                        continue
                    target = rg if m["match_type"] == "resource_group" else rkey
                    if target and fnmatchcase(target, m["pattern"]):
                        status = m["allocation_status"]
                        if app_id is None and (m["application_id"] is not None or status in ("shared", "unallocated")):
                            app_id = m["application_id"]
                            src_app = f"rg_rule:{m['id']}"
                        if env_id is None and m["environment_id"] is not None:
                            env_id = m["environment_id"]
                            src_env = f"rg_rule:{m['id']}"
                        break
                if status in ("shared", "unallocated"):
                    break  # explicit shared/unallocated classification ends the search
            elif source == "subscription":
                sub = self.subscriptions.get(sub_fk)
                if sub:
                    if app_id is None and sub[0] is not None:
                        app_id, src_app = sub[0], "subscription"
                    if env_id is None and sub[1] is not None:
                        env_id, src_env = sub[1], "subscription"
            elif source == "resource_tag":
                if app_id is None and tag_vals.get("application"):
                    aid = self.applications.get(tag_vals["application"].lower())
                    if aid is not None:
                        app_id, src_app = aid, "tag"
                if env_id is None and tag_vals.get("environment"):
                    code = self._env_code_from_value(tag_vals["environment"])
                    if code and code in self.environments:
                        env_id, src_env = self.environments[code], "tag"

        if env_id is None:
            env_id = self.environments.get("shared" if status == "shared" else "unallocated")
        env_group = self.environment_groups.get(env_id) if env_id is not None else None
        if status is None:
            if env_group == "shared":
                status = "shared"
            elif app_id is None:
                status = "unallocated"
            else:
                status = "allocated"
        if status in ("shared", "unallocated"):
            app_id = None  # shared / unallocated charges never belong to a single application

        cost_center = tag_vals.get("cost_center") or (row.get("cost_center_column") or None)
        return Allocation(
            application_id=app_id,
            environment_id=env_id,
            allocation_status=status,
            service_category=self.categorize(row),
            owner=tag_vals.get("owner"),
            cost_center=cost_center,
            project=tag_vals.get("project"),
            team=tag_vals.get("team"),
            business_unit=tag_vals.get("business_unit"),
            workload=tag_vals.get("workload"),
            source=f"app:{src_app};env:{src_env}",
        )


DEFAULT_CATEGORY_RULES: list[tuple[int, str, str, str]] = [
    # priority, match_field, pattern, category
    (10, "resource_group", "mc_*", "Azure Kubernetes Service"),
    (20, "resource_type", "microsoft.containerservice/*", "Azure Kubernetes Service"),
    (25, "meter_category", "azure kubernetes service", "Azure Kubernetes Service"),
    (30, "meter_category", "virtual machines*", "Virtual Machines"),
    (40, "meter_category", "sql database*", "Azure SQL"),
    (41, "meter_category", "sql managed instance*", "Azure SQL"),
    (42, "meter_category", "azure sql*", "Azure SQL"),
    (43, "resource_type", "microsoft.sql/*", "Azure SQL"),
    (50, "meter_category", "storage", "Storage"),
    (60, "meter_category", "bandwidth", "Networking"),
    (61, "meter_category", "virtual network", "Networking"),
    (62, "meter_category", "load balancer", "Networking"),
    (63, "meter_category", "application gateway", "Networking"),
    (64, "meter_category", "azure dns", "Networking"),
    (65, "meter_category", "azure front door*", "Networking"),
    (66, "meter_category", "nat gateway", "Networking"),
    (67, "meter_category", "vpn gateway", "Networking"),
    (68, "meter_category", "expressroute", "Networking"),
    (69, "meter_category", "azure firewall", "Networking"),
    (70, "meter_category", "network watcher", "Networking"),
    (71, "meter_category", "ip addresses", "Networking"),
    (72, "meter_category", "azure bastion", "Networking"),
    (73, "meter_category", "content delivery network", "Networking"),
    (74, "meter_category", "traffic manager", "Networking"),
    (75, "meter_category", "networking", "Networking"),
    (80, "meter_category", "log analytics", "Azure Monitor"),
    (81, "meter_category", "azure monitor", "Azure Monitor"),
    (82, "meter_category", "application insights", "Azure Monitor"),
    (83, "meter_category", "insight and analytics", "Azure Monitor"),
    (90, "meter_category", "azure app service", "App Service"),
    (91, "resource_type", "microsoft.web/*", "App Service"),
    (95, "meter_category", "key vault", "Key Vault"),
    (96, "meter_category", "container registry", "Container Registry"),
    # --- added in category rules v2 (seeded once into existing databases) ---
    (100, "meter_category", "azure synapse analytics", "Azure Synapse Analytics"),
    (101, "resource_type", "microsoft.synapse/*", "Azure Synapse Analytics"),
    (105, "meter_category", "azure databricks", "Azure Databricks"),
    (106, "resource_type", "microsoft.databricks/*", "Azure Databricks"),
    (110, "meter_category", "azure data factory*", "Azure Data Factory"),
    (111, "resource_type", "microsoft.datafactory/*", "Azure Data Factory"),
    (115, "meter_category", "event hubs", "Messaging & Integration"),
    (116, "meter_category", "service bus", "Messaging & Integration"),
    (117, "meter_category", "event grid", "Messaging & Integration"),
    (118, "meter_category", "logic apps", "Messaging & Integration"),
    (119, "meter_category", "api management", "Messaging & Integration"),
    (125, "meter_category", "azure database for postgresql", "Other Databases"),
    (126, "meter_category", "azure database for mysql", "Other Databases"),
    (127, "meter_category", "azure database for mariadb", "Other Databases"),
    (128, "meter_category", "azure cosmos db", "Other Databases"),
    (129, "meter_category", "redis cache", "Other Databases"),
    (130, "meter_category", "azure cache for redis", "Other Databases"),
]
CATEGORY_RULES_VERSION = 2

DEFAULT_TAG_MAPPINGS: list[tuple[str, str, int]] = [
    # tag key, target dimension, priority
    ("owner", "owner", 10),
    ("createdby", "owner", 20),
    ("costcenter", "cost_center", 10),
    ("cost-center", "cost_center", 11),
    ("cost_center", "cost_center", 12),
    ("project", "project", 10),
    ("team", "team", 10),
    ("businessunit", "business_unit", 10),
    ("business-unit", "business_unit", 11),
    ("workload", "workload", 10),
    ("application", "application", 10),
    ("app", "application", 20),
    ("environment", "environment", 10),
    ("env", "environment", 20),
]
