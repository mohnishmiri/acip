from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import Query

from app.services.params import ReportParams


def report_params(
    preset: str = Query("last_30_days", description="Date preset, e.g. last_30_days, week_to_date, previous_week, custom"),
    start_date: date | None = Query(None, description="Custom range start (preset=custom)"),
    end_date: date | None = Query(None, description="Custom range end (preset=custom)"),
    comparison: str = Query("previous_equivalent", description="none | previous_equivalent | previous_calendar | same_period_last_year | custom"),
    compare_start_date: date | None = None,
    compare_end_date: date | None = None,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    cost_type: Literal["actual", "amortized"] = "actual",
    currency: str | None = Query(None, min_length=3, max_length=3),
    as_of: date | None = Query(None, description="Override the as-of (latest data) date"),
    application: list[str] = Query(default=[], description="Application id, 'shared' or 'unallocated' (repeatable)"),
    environment: list[str] = Query(default=[], description="production | non_production | shared | unallocated | development | testing | uat"),
    subscription: list[str] = Query(default=[], description="Azure subscription GUID (repeatable)"),
    service_category: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    resource_group: list[str] = Query(default=[]),
    resource: list[str] = Query(default=[], description="Resource id (repeatable)"),
    resource_type: list[str] = Query(default=[]),
    owner: list[str] = Query(default=[]),
    cost_center: list[str] = Query(default=[]),
    meter_category: list[str] = Query(default=[]),
    meter_name: list[str] = Query(default=[]),
    sku: list[str] = Query(default=[]),
    charge_type: list[str] = Query(default=[]),
    pricing_model: list[str] = Query(default=[]),
    tag: list[str] = Query(default=[], description="key=value (repeatable)"),
    search: str | None = Query(None, max_length=200),
    group_by: str = "service_category",
    tag_key: str | None = None,
    top_n: int | None = Query(None, ge=1, le=50),
    sort: str = "abs_diff",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
) -> ReportParams:
    return ReportParams(
        preset=preset, start_date=start_date, end_date=end_date, comparison=comparison, compare_start_date=compare_start_date,
        compare_end_date=compare_end_date, granularity=granularity, cost_type=cost_type, currency=currency, as_of=as_of,
        application=application, environment=environment, subscription=subscription, service_category=service_category,
        region=region, resource_group=resource_group, resource=resource, resource_type=resource_type, owner=owner,
        cost_center=cost_center, meter_category=meter_category, meter_name=meter_name, sku=sku, charge_type=charge_type,
        pricing_model=pricing_model, tag=tag, search=search, group_by=group_by, tag_key=tag_key, top_n=top_n, sort=sort,
        page=page, page_size=page_size,
    )
