"""Reporting query builder over the pre-aggregated cost tables.

``CostRepository`` chooses the coarsest table that contains every dimension needed by the
requested grouping and filters:

    monthly_cost_aggregates  (month grain, coarse dims; only for whole-month ranges)
    daily_cost_aggregates    (day grain, coarse dims)
    resource_cost_aggregates (day x resource)
    meter_cost_aggregates    (day x resource x meter)
    cost_records             (raw; only for dimensions not pre-aggregated, e.g. tag + meter)

All filtering, grouping and aggregation happens in PostgreSQL; only aggregated rows are
returned. Every query is restricted to one dataset (actual / amortized) and one billing
currency -- the two are never summed together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, and_, cast, func, literal_column, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.schema import Table

from app.analytics.periods import Period, month_end
from app.models import CostRecord, DailyCostAggregate, MeterCostAggregate, MonthlyCostAggregate, ResourceCostAggregate

NONE_TOKEN = "__none__"

COARSE_DIMS = {
    "application",
    "environment",
    "subscription",
    "service_category",
    "region",
    "charge_type",
    "pricing_model",
    "owner",
    "cost_center",
    "currency",
}
RESOURCE_DIMS = COARSE_DIMS | {"resource_group", "resource", "resource_type", "tag", "search"}
METER_DIMS = (RESOURCE_DIMS - {"tag"}) | {"meter_category", "meter_subcategory", "meter_name", "meter", "sku", "unit"}
RAW_DIMS = RESOURCE_DIMS | METER_DIMS

DIM_COLUMNS: dict[str, tuple[str, ...]] = {
    "application": ("application_id", "allocation_status"),
    "environment": ("environment_id",),
    "subscription": ("subscription_fk",),
    "service_category": ("service_category",),
    "region": ("region",),
    "charge_type": ("charge_type",),
    "pricing_model": ("pricing_model",),
    "owner": ("owner",),
    "cost_center": ("cost_center",),
    "currency": ("billing_currency",),
    "resource_group": ("resource_group",),
    "resource": ("resource_key",),
    "resource_type": ("resource_type",),
    "meter_category": ("meter_category",),
    "meter_subcategory": ("meter_subcategory",),
    "meter_name": ("meter_name",),
    # meter = tier/subcategory + name: keeps e.g. GP vs Business Critical "vCore" apart (display-only, not a filter)
    "meter": ("meter_subcategory", "meter_name"),
    "sku": ("sku",),
    "unit": ("unit_of_measure",),
}

GROUP_BY_OPTIONS: dict[str, str] = {
    "application": "Application",
    "environment": "Environment",
    "subscription": "Subscription",
    "service_category": "Azure Service",
    "resource_group": "Resource Group",
    "resource": "Resource Name",
    "resource_type": "Resource Type",
    "meter_category": "Meter Category",
    "meter_name": "Meter Name",
    "meter": "Meter (incl. tier)",
    "region": "Region",
    "sku": "SKU",
    "cost_center": "Cost Center",
    "owner": "Owner",
    "charge_type": "Charge Type",
    "pricing_model": "Pricing Model",
    "tag": "Resource Tag",
}


@dataclass
class TableSpec:
    name: str
    table: Table
    dims: set[str]
    grain: str  # day | month
    has_quantity: bool
    raw: bool = False


TABLES = [
    TableSpec("monthly", MonthlyCostAggregate.__table__, COARSE_DIMS, "month", False),
    TableSpec("daily", DailyCostAggregate.__table__, COARSE_DIMS, "day", False),
    TableSpec("resource", ResourceCostAggregate.__table__, RESOURCE_DIMS, "day", False),
    TableSpec("meter", MeterCostAggregate.__table__, METER_DIMS, "day", True),
    TableSpec("raw", CostRecord.__table__, RAW_DIMS, "day", True, raw=True),
]


@dataclass
class CostFilters:
    dataset_type: str = "actual"
    currency: str | None = None
    application_ids: list[int] | None = None
    allocation_statuses: list[str] | None = None  # shared / unallocated (from the application filter)
    environment_ids: list[int] | None = None
    subscription_fks: list[int] | None = None
    service_categories: list[str] | None = None
    regions: list[str] | None = None
    resource_groups: list[str] | None = None
    resource_keys: list[str] | None = None
    resource_types: list[str] | None = None
    owners: list[str] | None = None
    cost_centers: list[str] | None = None
    meter_categories: list[str] | None = None
    meter_names: list[str] | None = None
    skus: list[str] | None = None
    charge_types: list[str] | None = None
    pricing_models: list[str] | None = None
    exclude_charge_types: list[str] | None = None
    tags: list[tuple[str, str]] | None = None
    search: str | None = None
    allowed_subscription_fks: set[int] | None = None  # RBAC scope (None = unrestricted)

    def required_dims(self) -> set[str]:
        need: set[str] = set()
        if self.application_ids or self.allocation_statuses:
            need.add("application")
        if self.environment_ids:
            need.add("environment")
        if self.subscription_fks or self.allowed_subscription_fks is not None:
            need.add("subscription")
        mapping = {
            "service_categories": "service_category",
            "regions": "region",
            "resource_groups": "resource_group",
            "resource_keys": "resource",
            "resource_types": "resource_type",
            "owners": "owner",
            "cost_centers": "cost_center",
            "meter_categories": "meter_category",
            "meter_names": "meter_name",
            "skus": "sku",
            "charge_types": "charge_type",
            "pricing_models": "pricing_model",
            "exclude_charge_types": "charge_type",
            "tags": "tag",
            "search": "search",
        }
        for attr, dim in mapping.items():
            if getattr(self, attr):
                need.add(dim)
        return need


@dataclass
class GroupRow:
    values: dict[str, Any]
    label_hint: str | None
    current: Decimal
    previous: Decimal
    current_records: int
    previous_records: int
    current_qty: Decimal | None = None
    previous_qty: Decimal | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _is_month_aligned(p: Period) -> bool:
    return p.start.day == 1 and p.end == month_end(p.end)


def _str_filter(col, values: list[str]) -> ColumnElement[bool]:
    real = [v for v in values if v != NONE_TOKEN]
    conds = []
    if real:
        conds.append(col.in_(real))
    if NONE_TOKEN in values:
        conds.append(col.is_(None))
    return or_(*conds) if len(conds) > 1 else conds[0]


class CostRepository:
    def __init__(self, db: Session, week_start_isodow: int = 1):
        self.db = db
        self.week_start = int(week_start_isodow)
        if not 1 <= self.week_start <= 7:
            raise ValueError("invalid week start")

    # -------------------------------------------------------------------------------
    def choose_table(self, dims: set[str], *, periods: Sequence[Period] = (), granularity: str | None = None) -> TableSpec:
        for spec in TABLES:
            if not dims <= spec.dims:
                continue
            if spec.grain == "month":
                if not periods or not all(_is_month_aligned(p) for p in periods):
                    continue
                if granularity not in (None, "monthly"):
                    continue
            return spec
        raise ValueError(f"No table supports dimensions {sorted(dims)}")

    def _where(self, t: Table, f: CostFilters, spec: TableSpec) -> list[ColumnElement[bool]]:
        c = t.c
        w: list[ColumnElement[bool]] = [c.dataset_type == f.dataset_type]
        if f.currency:
            w.append(c.billing_currency == f.currency)
        if f.allowed_subscription_fks is not None:
            w.append(c.subscription_fk.in_(list(f.allowed_subscription_fks) or [-1]))
        if f.subscription_fks:
            w.append(c.subscription_fk.in_(f.subscription_fks))
        if f.application_ids or f.allocation_statuses:
            conds = []
            if f.application_ids:
                conds.append(c.application_id.in_(f.application_ids))
            if f.allocation_statuses:
                conds.append(c.allocation_status.in_(f.allocation_statuses))
            w.append(or_(*conds))
        if f.environment_ids:
            w.append(c.environment_id.in_(f.environment_ids))
        for attr, col in (
            ("service_categories", "service_category"),
            ("regions", "region"),
            ("charge_types", "charge_type"),
            ("pricing_models", "pricing_model"),
            ("owners", "owner"),
            ("cost_centers", "cost_center"),
            ("resource_groups", "resource_group"),
            ("resource_keys", "resource_key"),
            ("resource_types", "resource_type"),
            ("meter_categories", "meter_category"),
            ("meter_names", "meter_name"),
            ("skus", "sku"),
        ):
            vals = getattr(f, attr)
            if vals:
                w.append(_str_filter(c[col], vals))
        if f.exclude_charge_types:
            w.append(or_(c.charge_type.is_(None), c.charge_type.notin_(f.exclude_charge_types)))
        if f.tags:
            for k, v in f.tags:
                if v == NONE_TOKEN:
                    w.append(or_(c.tags.is_(None), ~c.tags.has_key(k)))
                else:
                    w.append(c.tags[k].astext == v)
        if f.search:
            like = f"%{f.search.strip().lower()}%"
            w.append(or_(func.lower(c.resource_name).like(like), c.resource_key.like(like)))
        return w

    def _cost_cols(self, t: Table, spec: TableSpec):
        count_expr = func.count() if spec.raw else func.sum(t.c.record_count)
        return t.c.cost, count_expr, (t.c.record_count if not spec.raw else None)

    def _group_cols(self, t: Table, dims: list[str], tag_key: str | None) -> list[ColumnElement[Any]]:
        cols: list[ColumnElement[Any]] = []
        for d in dims:
            if d == "tag":
                cols.append(t.c.tags[tag_key or ""].astext.label("tag_value"))
            else:
                for cname in DIM_COLUMNS[d]:
                    cols.append(t.c[cname])
        return cols

    # -------------------------------------------------------------------------------
    def grouped_compare(
        self,
        f: CostFilters,
        current: Period,
        previous: Period | None,
        group_dims: list[str],
        *,
        tag_key: str | None = None,
        with_quantity: bool = False,
        resource_attributes: bool = False,
        limit: int | None = None,
    ) -> list[GroupRow]:
        needed = set(group_dims) | f.required_dims()
        if with_quantity:
            needed |= {"meter_name"}
        periods = [current] + ([previous] if previous else [])
        spec = self.choose_table(needed, periods=periods)
        t = spec.table
        c = t.c
        in_cur = c.usage_date.between(current.start, current.end)
        in_prev = c.usage_date.between(previous.start, previous.end) if previous else None
        date_cond = or_(in_cur, in_prev) if previous else in_cur

        group_cols = self._group_cols(t, group_dims, tag_key)
        rec = (lambda cond: func.count().filter(cond)) if spec.raw else (lambda cond: func.coalesce(func.sum(c.record_count).filter(cond), 0))
        cols: list[Any] = list(group_cols)
        cols += [
            func.coalesce(func.sum(c.cost).filter(in_cur), 0).label("cur_cost"),
            rec(in_cur).label("cur_records"),
        ]
        if previous:
            cols += [func.coalesce(func.sum(c.cost).filter(in_prev), 0).label("prev_cost"), rec(in_prev).label("prev_records")]
        if with_quantity and spec.has_quantity:
            cols.append(func.coalesce(func.sum(c.quantity).filter(in_cur), 0).label("cur_qty"))
            if previous:
                cols.append(func.coalesce(func.sum(c.quantity).filter(in_prev), 0).label("prev_qty"))
        if "resource" in group_dims and spec.name in ("resource", "meter", "raw"):
            cols.append(func.max(c.resource_name).label("label_hint"))
        if resource_attributes and spec.name in ("resource", "meter", "raw"):
            cols += [
                func.max(c.subscription_fk).label("attr_subscription_fk"),
                func.max(c.resource_group).label("attr_resource_group"),
                func.max(c.resource_type).label("attr_resource_type"),
                func.max(c.region).label("attr_region"),
                func.max(c.service_category).label("attr_service_category"),
                func.max(c.application_id).label("attr_application_id"),
                func.max(c.environment_id).label("attr_environment_id"),
                func.max(c.allocation_status).label("attr_allocation_status"),
                func.max(c.owner).label("attr_owner"),
                func.max(c.cost_center).label("attr_cost_center"),
            ]
        stmt = select(*cols).where(and_(*self._where(t, f, spec)), date_cond)
        if group_cols:
            stmt = stmt.group_by(*group_cols)
        stmt = stmt.order_by(literal_column("cur_cost").desc())
        if limit:
            stmt = stmt.limit(limit)
        out: list[GroupRow] = []
        for r in self.db.execute(stmt).mappings():
            values = {}
            for d in group_dims:
                if d == "tag":
                    values["tag_value"] = r["tag_value"]
                else:
                    for cname in DIM_COLUMNS[d]:
                        values[cname] = r[cname]
            extra = {k[5:]: v for k, v in r.items() if k.startswith("attr_")}
            out.append(
                GroupRow(
                    values=values,
                    label_hint=r.get("label_hint"),
                    current=Decimal(r["cur_cost"]),
                    previous=Decimal(r["prev_cost"]) if previous else Decimal(0),
                    current_records=int(r["cur_records"] or 0),
                    previous_records=int(r["prev_records"] or 0) if previous else 0,
                    current_qty=Decimal(r["cur_qty"]) if "cur_qty" in r else None,
                    previous_qty=Decimal(r["prev_qty"]) if "prev_qty" in r else None,
                    extra=extra,
                )
            )
        return out

    def bucket_expr(self, t: Table, granularity: str, spec: TableSpec):
        if spec.grain == "month" or granularity == "monthly":
            return cast(func.date_trunc("month", t.c.usage_date), Date)
        if granularity == "weekly":
            ws = self.week_start
            return literal_column(
                f"({t.name}.usage_date - ((EXTRACT(ISODOW FROM {t.name}.usage_date)::int - {ws} + 7) % 7))", Date
            )
        return t.c.usage_date

    def series(
        self,
        f: CostFilters,
        period: Period,
        granularity: str,
        group_dims: list[str] | None = None,
        *,
        tag_key: str | None = None,
        with_quantity: bool = False,
    ) -> list[dict[str, Any]]:
        group_dims = group_dims or []
        needed = set(group_dims) | f.required_dims()
        if with_quantity:
            needed |= {"meter_name"}
        spec = self.choose_table(needed, periods=[period], granularity=granularity)
        t = spec.table
        bucket = self.bucket_expr(t, granularity, spec).label("bucket")
        group_cols = self._group_cols(t, group_dims, tag_key)
        cols = [bucket, *group_cols, func.sum(t.c.cost).label("cost")]
        if with_quantity and spec.has_quantity:
            cols.append(func.sum(t.c.quantity).label("quantity"))
        stmt = (
            select(*cols)
            .where(and_(*self._where(t, f, spec)), t.c.usage_date.between(period.start, period.end))
            .group_by(bucket, *group_cols)
            .order_by(bucket)
        )
        return [dict(r) for r in self.db.execute(stmt).mappings()]

    def daily_totals(self, f: CostFilters, start: date, end: date) -> dict[date, Decimal]:
        rows = self.series(f, Period(start, end), "daily")
        return {r["bucket"]: Decimal(r["cost"]) for r in rows}

    def total(self, f: CostFilters, period: Period) -> Decimal:
        rows = self.grouped_compare(f, period, None, [])
        return rows[0].current if rows else Decimal(0)

    def date_bounds(self, f: CostFilters) -> tuple[date | None, date | None]:
        """Earliest and latest usage date with data for the scope (coarse filters only)."""
        coarse = CostFilters(
            dataset_type=f.dataset_type,
            currency=f.currency,
            subscription_fks=f.subscription_fks,
            application_ids=f.application_ids,
            allocation_statuses=f.allocation_statuses,
            environment_ids=f.environment_ids,
            allowed_subscription_fks=f.allowed_subscription_fks,
        )
        t = DailyCostAggregate.__table__
        spec = TABLES[1]
        row = self.db.execute(select(func.min(t.c.usage_date), func.max(t.c.usage_date)).where(and_(*self._where(t, coarse, spec)))).first()
        return (row[0], row[1]) if row else (None, None)

    def currency_totals(self, f: CostFilters, period: Period) -> list[tuple[str, Decimal]]:
        g = CostFilters(**{**f.__dict__, "currency": None})
        rows = self.grouped_compare(g, period, None, ["currency"])
        return sorted(((r.values["billing_currency"], r.current) for r in rows), key=lambda x: -x[1])

    def subscription_latest_dates(self, dataset_type: str) -> dict[int, date]:
        t = DailyCostAggregate.__table__
        rows = self.db.execute(
            select(t.c.subscription_fk, func.max(t.c.usage_date)).where(t.c.dataset_type == dataset_type).group_by(t.c.subscription_fk)
        ).all()
        return {r[0]: r[1] for r in rows}

    def distinct_values(self, column: str, f: CostFilters, limit: int = 500) -> list[str]:
        dim = next((d for d, cols in DIM_COLUMNS.items() if cols == (column,)), None)
        needed = ({dim} if dim else set()) | f.required_dims()
        spec = self.choose_table(needed)
        t = spec.table
        stmt = (
            select(t.c[column]).where(and_(*self._where(t, f, spec)), t.c[column].is_not(None)).group_by(t.c[column]).order_by(t.c[column]).limit(limit)
        )
        return [r[0] for r in self.db.execute(stmt)]

    def tag_keys(self, limit: int = 200) -> list[str]:
        t = ResourceCostAggregate.__table__
        stmt = (
            select(func.jsonb_object_keys(t.c.tags).label("k"))
            .where(t.c.tags.is_not(None))
            .distinct()
            .order_by("k")
            .limit(limit)
        )
        return [r[0] for r in self.db.execute(stmt)]


__all__ = [
    "CostFilters",
    "CostRepository",
    "GROUP_BY_OPTIONS",
    "GroupRow",
    "NONE_TOKEN",
    "TableSpec",
]
