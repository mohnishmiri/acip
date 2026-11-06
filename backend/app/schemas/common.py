"""Pydantic request / response models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Envelope(BaseModel):
    """Standard response envelope for reporting endpoints.

    ``data`` holds the payload; ``meta`` always describes the reporting context: as-of date,
    resolved periods, currency, cost type, demo flag, warnings and pagination when relevant.
    """

    data: Any
    meta: dict[str, Any] | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ExportDefinitionIn(BaseModel):
    dataset_type: Literal["actual", "amortized", "focus"]
    export_name: str = Field(min_length=1, max_length=200)
    container: str = Field(min_length=3, max_length=63)
    root_folder_path: str = Field(default="", max_length=500)
    storage_account_url: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class SubscriptionIn(BaseModel):
    subscription_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    subscription_name: str = Field(min_length=1, max_length=200)
    application_id: int | None = None
    environment: Literal["production", "non_production", "development", "testing", "uat", "shared", "unallocated"]
    tenant_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")
    billing_currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    enabled: bool = True
    exports: list[ExportDefinitionIn] | None = None


class SubscriptionPatch(BaseModel):
    subscription_name: str | None = None
    application_id: int | None = None
    environment: str | None = None
    tenant_id: str | None = None
    billing_currency: str | None = None
    enabled: bool | None = None
    exports: list[ExportDefinitionIn] | None = None


class ApplicationIn(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")  # e.g. "app1" or "ATTCC"
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = None
    is_active: bool = True
    sort_order: int = 100


class BudgetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scope_type: Literal["total", "application", "subscription", "environment", "resource_group"]
    scope_ref: str | None = None
    period_type: Literal["monthly", "annual"]
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    cost_type: Literal["actual", "amortized"] = "actual"
    start_date: date
    end_date: date | None = None
    thresholds: list[float] = Field(default_factory=lambda: [70, 80, 90, 100])
    forecast_alert: bool = True
    enabled: bool = True
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class StatusUpdate(BaseModel):
    status: str
    comment: str | None = Field(default=None, max_length=4000)


class CommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=4000)


class IngestionTrigger(BaseModel):
    subscription_ids: list[str] | None = Field(default=None, description="Subscriptions to synchronise (default: all enabled)")
    force: bool = Field(default=False, description="Re-process runs even if already applied")
    period_from: date | None = None
    period_to: date | None = None
    dataset_types: list[Literal["actual", "amortized", "focus"]] | None = None


class ReprocessRequest(BaseModel):
    subscription_id: str
    period_from: date
    period_to: date
    dataset_types: list[Literal["actual", "amortized", "focus"]] | None = None


class LocalExportRequest(BaseModel):
    subscription_ids: list[str] | None = Field(default=None, description="Subscriptions to pull (default: all enabled, non-demo)")
    months: int = Field(default=3, ge=1, le=13, description="Calendar months to pull, ending with the current month (ignored when start_date is given)")
    start_date: date | None = None
    end_date: date | None = None
    dataset_types: list[Literal["actual", "amortized"]] = Field(default_factory=lambda: ["actual", "amortized"])


class BackfillRequest(BaseModel):
    subscription_id: str
    metric: Literal["ActualCost", "AmortizedCost"] = "ActualCost"
    start_date: date
    end_date: date


class ConnectionTestRequest(BaseModel):
    subscription_ids: list[str] | None = None


class SettingUpdate(BaseModel):
    value: Any


class TagMappingIn(BaseModel):
    tag_key: str = Field(min_length=1, max_length=200)
    tag_value: str | None = None
    target_dimension: Literal["application", "environment", "owner", "cost_center", "project", "team", "business_unit", "workload"]
    target_value: str | None = None
    priority: int = 100
    enabled: bool = True
    description: str | None = None


class AppMappingIn(BaseModel):
    match_type: Literal["resource_group", "resource_id"]
    pattern: str = Field(min_length=1, max_length=500)
    subscription_id: str | None = None
    application_id: int | None = None
    environment: str | None = None
    allocation_status: Literal["allocated", "shared", "unallocated"] = "allocated"
    priority: int = 100
    enabled: bool = True
    description: str | None = None


class CategoryRuleIn(BaseModel):
    match_field: Literal["resource_group", "resource_type", "meter_category", "meter_subcategory", "meter_name", "service_name", "consumed_service"]
    pattern: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=100)
    priority: int = 100
    enabled: bool = True
    description: str | None = None


class AnomalyRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    filters: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    alert_type: Literal["anomaly", "budget_threshold", "budget_forecast", "ingestion_failure", "data_delay", "savings_opportunity"]
    min_severity: Literal["informational", "low", "medium", "high", "critical"] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    channels: list[Literal["in_app", "teams", "email"]] = Field(default_factory=lambda: ["in_app"])
    cooldown_hours: int = 24
    enabled: bool = True


class RoleAssignmentIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=200, description="Entra object id (oid)")
    email: str | None = None
    display_name: str | None = None
    role: Literal["administrator", "finops_analyst", "engineering_lead", "viewer"]
    application_id: int | None = None


class SavedComparisonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    params: dict[str, Any] = Field(description="Query parameters of the comparison view (re-run against current data)")


class MarkRead(BaseModel):
    ids: list[int] | None = None


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
