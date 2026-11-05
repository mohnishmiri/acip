"""Request parameters shared by all reporting endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ReportParams:
    preset: str = "last_30_days"
    start_date: date | None = None
    end_date: date | None = None
    comparison: str = "previous_equivalent"
    compare_start_date: date | None = None
    compare_end_date: date | None = None
    granularity: str = "daily"
    cost_type: str = "actual"
    currency: str | None = None
    as_of: date | None = None

    application: list[str] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    subscription: list[str] = field(default_factory=list)
    service_category: list[str] = field(default_factory=list)
    region: list[str] = field(default_factory=list)
    resource_group: list[str] = field(default_factory=list)
    resource: list[str] = field(default_factory=list)
    resource_type: list[str] = field(default_factory=list)
    owner: list[str] = field(default_factory=list)
    cost_center: list[str] = field(default_factory=list)
    meter_category: list[str] = field(default_factory=list)
    meter_name: list[str] = field(default_factory=list)
    sku: list[str] = field(default_factory=list)
    charge_type: list[str] = field(default_factory=list)
    pricing_model: list[str] = field(default_factory=list)
    tag: list[str] = field(default_factory=list)  # "key=value"
    search: str | None = None

    group_by: str = "service_category"
    tag_key: str | None = None
    top_n: int | None = None
    sort: str = "abs_diff"
    page: int = 1
    page_size: int = 50

    def copy(self, **changes) -> ReportParams:
        data = {k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}
        data.update(changes)
        return ReportParams(**data)
