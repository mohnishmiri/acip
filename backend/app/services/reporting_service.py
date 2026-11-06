"""Reporting service: scope resolution + cost explorer / comparison / KPI payloads.

Every reporting endpoint goes through ``ReportingService`` so period handling, currency
handling, the comparison formulas and waterfall reconciliation are identical everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import periods as P
from app.analytics.comparison import (
    ZERO,
    ComparedItem,
    build_waterfall,
    compute_metrics,
    compute_totals,
    money,
    pct_change,
    pct_out,
    qty,
    sort_items,
)
from app.core.errors import ValidationFailed
from app.models import AzureSubscription, SavingsOpportunity
from app.repositories.cost_repository import GROUP_BY_OPTIONS, NONE_TOKEN, CostFilters, CostRepository, GroupRow
from app.services import settings_service
from app.services.labels import LabelResolver
from app.services.params import ReportParams

ENV_GROUP_CODES = {"production", "non_production", "shared", "unallocated"}
SORTS = {"abs_diff", "pct_increase", "largest_decrease", "largest_increase", "current_cost", "previous_cost", "contribution", "name"}
MAX_GROUPS = 500
MAX_SERIES = 8  # categorical palette has 8 validated slots; the rest folds into "Other"

# Drill-down hierarchy used by the Cost Explorer and the Comparison page.
DRILL_PATH = ["application", "environment", "subscription", "service_category", "resource_group", "resource", "meter_name"]
NEXT_LEVEL = {
    "application": "environment",
    "environment": "subscription",
    "subscription": "service_category",
    "service_category": "resource",
    "resource_group": "resource",
    "resource_type": "resource",
    "region": "service_category",
    "meter_category": "meter_name",
    "owner": "resource",
    "cost_center": "resource",
    "tag": "resource",
    "charge_type": "service_category",
    "pricing_model": "service_category",
    "sku": "resource",
    "meter_name": None,
    "meter": None,
    "resource": None,
}
# group-by dimension -> ReportParams attribute used when the user clicks a group
FILTER_PARAM = {
    "application": "application",
    "environment": "environment",
    "subscription": "subscription",
    "service_category": "service_category",
    "resource_group": "resource_group",
    "resource": "resource",
    "resource_type": "resource_type",
    "meter_category": "meter_category",
    "meter_name": "meter_name",
    "region": "region",
    "sku": "sku",
    "cost_center": "cost_center",
    "owner": "owner",
    "charge_type": "charge_type",
    "pricing_model": "pricing_model",
    "tag": "tag",
}


@dataclass
class Scope:
    filters: CostFilters
    current: P.ResolvedPeriod
    comparison: P.Period | None
    as_of: date
    currency: str
    warnings: list[str] = field(default_factory=list)
    is_demo: bool = False
    data_start: date | None = None
    data_end: date | None = None
    other_currencies: list[dict[str, Any]] = field(default_factory=list)


def period_out(p: P.Period | None, resolved: P.ResolvedPeriod | None = None) -> dict[str, Any] | None:
    if p is None:
        return None
    out = {"start": p.start.isoformat(), "end": p.end.isoformat(), "days": p.days, "label": p.label, "description": P.describe(p.start, p.end)}
    if resolved is not None:
        out.update(
            preset=resolved.preset,
            unit=resolved.unit,
            nominal_start=resolved.nominal_start.isoformat(),
            nominal_end=resolved.nominal_end.isoformat(),
            is_incomplete=resolved.is_incomplete,
        )
    return out


def item_out(i: ComparedItem, comparison: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": i.key,
        "label": i.label,
        "current": money(i.current),
        "current_records": i.current_records,
        "share_of_total": pct_out(i.share_of_total),
        "current_daily_avg": money(i.current_daily_avg),
    }
    if comparison:
        out.update(
            previous=money(i.previous),
            previous_records=i.previous_records,
            diff=money(i.diff),
            pct=pct_out(i.pct),
            status=i.status,
            contribution_pct=pct_out(i.contribution_pct),
            previous_daily_avg=money(i.previous_daily_avg),
        )
    if i.current_quantity is not None or i.previous_quantity is not None:
        out.update(
            current_quantity=qty(i.current_quantity),
            previous_quantity=qty(i.previous_quantity),
            quantity_diff=qty(i.quantity_diff),
            quantity_pct=pct_out(i.quantity_pct),
            unit=i.unit,
        )
    if i.attributes:
        out["attributes"] = i.attributes
    return out


def waterfall_out(w) -> dict[str, Any]:
    return {
        "previous_total": money(w.previous_total),
        "current_total": money(w.current_total),
        "net_change": money(w.net_change),
        "pct_change": pct_out(pct_change(w.previous_total, w.current_total)),
        "reconciled": w.reconciled,
        "reconciliation_difference": money(w.reconciliation_difference, 6),
        "top_n": w.top_n,
        "other_member_count": w.other_member_count,
        "steps": [
            {
                "key": s.key,
                "label": s.label,
                "kind": s.kind,
                "value": money(s.value),
                "start": money(s.start),
                "end": money(s.end),
                "previous": money(s.previous),
                "current": money(s.current),
                "pct": pct_out(s.pct),
                "status": s.status,
                "member_count": s.member_count,
            }
            for s in w.steps
        ],
    }


class ReportingService:
    def __init__(self, db: Session, params: ReportParams, allowed_subscription_fks: set[int] | None = None):
        self.db = db
        self.params = params
        self.allowed = allowed_subscription_fks
        self.week_start = settings_service.week_start(db)
        self.labels = LabelResolver(db)
        self.repo = CostRepository(db, self.week_start)
        self._scope: Scope | None = None
        self._validate()

    # ------------------------------------------------------------------ validation --
    def _validate(self) -> None:
        p = self.params
        if p.preset not in P.PRESETS:
            raise ValidationFailed(f"Unknown date preset '{p.preset}'", details={"allowed": list(P.PRESETS)})
        if p.comparison not in P.COMPARISON_MODES:
            raise ValidationFailed(f"Unknown comparison '{p.comparison}'", details={"allowed": list(P.COMPARISON_MODES)})
        if p.granularity not in ("daily", "weekly", "monthly"):
            raise ValidationFailed("granularity must be daily, weekly or monthly")
        if p.cost_type not in ("actual", "amortized"):
            raise ValidationFailed("cost_type must be 'actual' or 'amortized'")
        if p.group_by not in GROUP_BY_OPTIONS:
            raise ValidationFailed(f"Unknown group_by '{p.group_by}'", details={"allowed": list(GROUP_BY_OPTIONS)})
        if p.group_by == "tag" and not p.tag_key:
            raise ValidationFailed("group_by=tag requires tag_key")
        if p.sort not in SORTS:
            raise ValidationFailed(f"Unknown sort '{p.sort}'", details={"allowed": sorted(SORTS)})
        # The HTTP layer caps page_size at 1,000; exports use larger internal pages.
        if p.page < 1 or not 1 <= p.page_size <= 100_000:
            raise ValidationFailed("page must be >= 1 and page_size between 1 and 100000")

    # ------------------------------------------------------------------ filters -----
    def build_filters(self, params: ReportParams | None = None) -> CostFilters:
        p = params or self.params
        f = CostFilters(dataset_type=p.cost_type, allowed_subscription_fks=self.allowed)
        app_ids: list[int] = []
        statuses: list[str] = []
        for v in p.application:
            if v in ("shared", "unallocated"):
                statuses.append(v)
            elif v.isdigit():
                app_ids.append(int(v))
            else:
                match = next((a.id for a in self.labels.apps.values() if a.code == v), None)
                if match is None:
                    raise ValidationFailed(f"Unknown application '{v}'")
                app_ids.append(match)
        f.application_ids = app_ids or None
        f.allocation_statuses = statuses or None

        env_ids: set[int] = set()
        for code in p.environment:
            if code in ENV_GROUP_CODES:
                env_ids |= {e.id for e in self.labels.envs.values() if e.environment_group == code}
            elif code in self.labels.env_by_code:
                env_ids.add(self.labels.env_by_code[code].id)
            else:
                raise ValidationFailed(f"Unknown environment '{code}'")
        if p.environment:
            f.environment_ids = sorted(env_ids) or [-1]

        sub_fks = []
        for guid in p.subscription:
            s = self.labels.sub_by_guid.get(guid.lower())
            if s is None:
                raise ValidationFailed(f"Unknown subscription '{guid}'")
            sub_fks.append(s.id)
        f.subscription_fks = sub_fks or None

        f.service_categories = p.service_category or None
        f.regions = p.region or None
        f.resource_groups = [v.lower() if v != NONE_TOKEN else v for v in p.resource_group] or None
        f.resource_keys = [v.lower() for v in p.resource] or None
        f.resource_types = [v.lower() if v != NONE_TOKEN else v for v in p.resource_type] or None
        f.owners = p.owner or None
        f.cost_centers = p.cost_center or None
        f.meter_categories = p.meter_category or None
        f.meter_names = p.meter_name or None
        f.skus = p.sku or None
        f.charge_types = p.charge_type or None
        f.pricing_models = p.pricing_model or None
        tags = []
        for t in p.tag:
            if "=" not in t:
                raise ValidationFailed(f"tag filter must be key=value, got '{t}'")
            k, _, v = t.partition("=")
            tags.append((k.strip(), v.strip()))
        f.tags = tags or None
        f.search = p.search.strip() if p.search and p.search.strip() else None
        return f

    # ------------------------------------------------------------------ scope -------
    def scope(self) -> Scope:
        if self._scope is not None:
            return self._scope
        p = self.params
        f = self.build_filters()
        warnings: list[str] = []
        data_start, data_end = self.repo.date_bounds(f)
        if p.as_of:
            as_of = p.as_of
        elif data_end:
            as_of = settings_service.complete_through(self.db, data_end) or data_end
            if as_of < data_end:
                warnings.append(
                    f"Usage after {as_of.isoformat()} (latest: {data_end.isoformat()}) is still being billed by Azure and is excluded from "
                    "relative periods, forecasts and comparisons until complete (setting reporting.data_completeness_lag_days)."
                )
        else:
            as_of = datetime.now(UTC).date()
            warnings.append("No billing data is available for the selected scope and cost type.")
        try:
            current = P.resolve_period(p.preset, as_of, week_start_isodow=self.week_start, custom_start=p.start_date, custom_end=p.end_date)
            comparison = P.resolve_comparison(current, p.comparison, custom_start=p.compare_start_date, custom_end=p.compare_end_date)
        except P.PeriodError as exc:
            raise ValidationFailed(str(exc)) from exc

        # Currency: never sum different billing currencies.
        periods = [current.period] + ([comparison] if comparison else [])
        span = P.Period(min(x.start for x in periods), max(x.end for x in periods))
        cur_totals = self.repo.currency_totals(f, span)
        currency = (p.currency or "").upper() or None
        other: list[dict[str, Any]] = []
        if currency is None:
            default = settings_service.get_setting(self.db, "reporting.default_currency")
            present = [c for c, _ in cur_totals]
            currency = default if default in present or not present else present[0]
        for c, total in cur_totals:
            if c != currency:
                other.append({"currency": c, "total": money(total)})
        if other:
            warnings.append(
                "The selected scope contains costs in other billing currencies that are excluded from these totals: "
                + ", ".join(f"{o['currency']} {o['total']:,.2f}" for o in other)
                + ". Select the currency to view them; currencies are never summed without an explicit conversion."
            )
        f.currency = currency

        if current.is_incomplete:
            warnings.append(
                f"The current period is incomplete: billing data is available through {as_of.isoformat()} "
                f"({current.elapsed_days} of {current.nominal_days} days)."
            )
        if comparison and data_start and comparison.start < data_start:
            warnings.append(
                f"The comparison period starts before the earliest available billing data ({data_start.isoformat()}); "
                "comparison values may be understated."
            )
        sub_ids = f.subscription_fks or list(self.labels.subs)
        if self.allowed is not None:
            sub_ids = [s for s in sub_ids if s in self.allowed]
        is_demo = any(self.labels.subs[s].is_demo for s in sub_ids if s in self.labels.subs)
        self._scope = Scope(f, current, comparison, as_of, currency, warnings, is_demo, data_start, data_end, other)
        return self._scope

    def meta(self, scope: Scope, **extra: Any) -> dict[str, Any]:
        p = self.params
        m = {
            "as_of": scope.as_of.isoformat(),
            "data_start": scope.data_start.isoformat() if scope.data_start else None,
            "data_end": scope.data_end.isoformat() if scope.data_end else None,
            "period": period_out(scope.current.period, scope.current),
            "comparison_period": period_out(scope.comparison),
            "comparison_mode": p.comparison,
            "currency": scope.currency,
            "cost_type": p.cost_type,
            "granularity": p.granularity,
            "week_start_isodow": self.week_start,
            "is_demo": scope.is_demo,
            "warnings": scope.warnings,
            "other_currencies": scope.other_currencies,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        m.update(extra)
        return m

    # ------------------------------------------------------------------ helpers -----
    def to_items(self, rows: list[GroupRow], dim: str) -> list[ComparedItem]:
        items = []
        for r in rows:
            key, label = self.labels.key_label(dim, r.values, r.label_hint)
            attrs = self.labels.describe_resource_attrs(r.extra) if r.extra else {}
            items.append(
                ComparedItem(
                    key=key,
                    label=label,
                    previous=r.previous,
                    current=r.current,
                    previous_records=r.previous_records,
                    current_records=r.current_records,
                    previous_quantity=r.previous_qty,
                    current_quantity=r.current_qty,
                    attributes=attrs,
                )
            )
        return items

    def compared_groups(self, scope: Scope, dim: str, *, resource_attributes: bool = False) -> tuple[list[ComparedItem], tuple[Decimal, Decimal, Decimal]]:
        rows = self.repo.grouped_compare(
            scope.filters, scope.current.period, scope.comparison, [dim], tag_key=self.params.tag_key, resource_attributes=resource_attributes
        )
        items = self.to_items(rows, dim)
        totals = compute_metrics(items, current_days=scope.current.period.days, previous_days=scope.comparison.days if scope.comparison else None)
        return items, totals

    def totals_out(self, scope: Scope, total_prev: Decimal, total_cur: Decimal) -> dict[str, Any]:
        t = compute_totals(
            total_prev if scope.comparison else None,
            total_cur,
            current_days=scope.current.period.days,
            previous_days=scope.comparison.days if scope.comparison else None,
            nominal_days=scope.current.nominal_days if scope.current.is_incomplete else None,
        )
        return {
            "current": money(t.current),
            "previous": money(t.previous) if scope.comparison else None,
            "diff": money(t.diff) if scope.comparison else None,
            "pct": pct_out(t.pct) if scope.comparison else None,
            "status": t.status if scope.comparison else None,
            "current_daily_avg": money(t.current_daily_avg),
            "previous_daily_avg": money(t.previous_daily_avg),
            "run_rate": money(t.run_rate),
            "significance": self.significance(t.previous, t.current, t.diff) if scope.comparison else None,
        }

    def significance(self, previous: Decimal, current: Decimal, diff: Decimal) -> str:
        """Distinguish normal variation from a meaningful movement (configurable)."""
        pct_thr = Decimal(str(settings_service.get_setting(self.db, "reporting.significant_change_pct")))
        abs_thr = Decimal(str(settings_service.get_setting(self.db, "reporting.significant_change_abs")))
        pct = pct_change(previous, current)
        if abs(diff) < abs_thr or (pct is not None and abs(pct) < pct_thr):
            return "normal"
        return "notable_increase" if diff > 0 else "notable_decrease"

    def top_n(self) -> int:
        return int(self.params.top_n or settings_service.get_setting(self.db, "reporting.default_waterfall_top_n"))

    # ------------------------------------------------------------------ series ------
    def series_payload(self, scope: Scope, group_dim: str | None, top_keys: list[str] | None = None) -> dict[str, Any]:
        g = self.params.granularity
        cur = scope.current.period
        buckets = P.buckets(cur, g, self.week_start)
        idx = {b: i for i, b in enumerate(buckets)}
        total = [Decimal(0)] * len(buckets)
        series: list[dict[str, Any]] = []
        if group_dim:
            rows = self.repo.series(scope.filters, cur, g, [group_dim], tag_key=self.params.tag_key)
            per: dict[str, dict[str, Any]] = {}
            for r in rows:
                key, label = self.labels.key_label(group_dim, r, None)
                s = per.setdefault(key, {"key": key, "label": label, "values": [Decimal(0)] * len(buckets), "sum": Decimal(0)})
                i = idx.get(r["bucket"])
                if i is not None:
                    s["values"][i] += Decimal(r["cost"])
                    s["sum"] += Decimal(r["cost"])
                    total[i] += Decimal(r["cost"])
            # resource labels come from the grouped query (series rows carry no name)
            ordered = sorted(per.values(), key=lambda s: -s["sum"])
            keep = top_keys[:MAX_SERIES] if top_keys else [s["key"] for s in ordered[:MAX_SERIES]]
            kept = [per[k] for k in keep if k in per]
            rest = [s for s in ordered if s["key"] not in set(keep)]
            for s in kept:
                series.append({"key": s["key"], "label": s["label"], "values": [money(v) for v in s["values"]]})
            if rest:
                vals = [sum((s["values"][i] for s in rest), Decimal(0)) for i in range(len(buckets))]
                series.append({"key": "__other__", "label": f"Other ({len(rest)})", "values": [money(v) for v in vals]})
        else:
            for r in self.repo.series(scope.filters, cur, g):
                i = idx.get(r["bucket"])
                if i is not None:
                    total[i] += Decimal(r["cost"])

        previous_total = None
        previous_buckets = None
        if scope.comparison:
            pb = P.buckets(scope.comparison, g, self.week_start)
            pidx = {b: i for i, b in enumerate(pb)}
            pvals = [Decimal(0)] * len(pb)
            for r in self.repo.series(scope.filters, scope.comparison, g):
                i = pidx.get(r["bucket"])
                if i is not None:
                    pvals[i] += Decimal(r["cost"])
            # align by position: bucket i of the current period vs bucket i of the comparison
            previous_total = [money(pvals[i]) if i < len(pvals) else None for i in range(len(buckets))]
            previous_buckets = [pb[i].isoformat() if i < len(pb) else None for i in range(len(buckets))]
        coverage = []
        for b in buckets:
            if g == "daily":
                be = b
            elif g == "weekly":
                be = b + timedelta(days=6)
            else:
                be = P.month_end(b)
            covered = (min(be, cur.end) - max(b, cur.start)).days + 1
            coverage.append([covered, (be - b).days + 1])
        return {
            "granularity": g,
            "buckets": [b.isoformat() for b in buckets],
            # [days of the bucket inside the period, days in the bucket] -- partial buckets must not read as a cost drop
            "coverage": coverage,
            "series": series,
            "total": [money(v) for v in total],
            "previous_total": previous_total,
            "previous_buckets": previous_buckets,
        }

    # ------------------------------------------------------------------ endpoints ---
    def explorer(self) -> dict[str, Any]:
        scope = self.scope()
        dim = self.params.group_by
        has_cmp = scope.comparison is not None
        items, (tp, tc, _) = self.compared_groups(scope, dim)
        sort = self.params.sort if has_cmp else ("current_cost" if self.params.sort in ("abs_diff", "pct_increase", "largest_decrease", "contribution", "largest_increase") else self.params.sort)
        items = sort_items(items, sort)
        truncated = len(items) > MAX_GROUPS
        shown = items[:MAX_GROUPS]
        if truncated:
            rest = items[MAX_GROUPS:]
            other = ComparedItem(key="__other__", label=f"Other ({len(rest)} more)", previous=sum((i.previous for i in rest), ZERO),
                                 current=sum((i.current for i in rest), ZERO))
            compute_metrics([*shown, other])  # keep shares relative to full total
            shown.append(other)
        top_keys = [i.key for i in sort_items(items, "current_cost")[:MAX_SERIES]]
        series = self.series_payload(scope, dim, top_keys)
        waterfall = waterfall_out(build_waterfall(items, tp, tc, self.top_n())) if has_cmp else None
        return {
            "data": {
                "group_by": dim,
                "group_by_label": GROUP_BY_OPTIONS[dim],
                "next_level": NEXT_LEVEL.get(dim),
                "filter_param": FILTER_PARAM.get(dim),
                "totals": self.totals_out(scope, tp, tc),
                "groups": [item_out(i, has_cmp) for i in shown],
                "group_count": len(items),
                "groups_truncated": truncated,
                "series": series,
                "waterfall": waterfall,
            },
            "meta": self.meta(scope),
        }

    def compare(self) -> dict[str, Any]:
        scope = self.scope()
        if scope.comparison is None:
            raise ValidationFailed("A comparison period is required (comparison must not be 'none').")
        dim = self.params.group_by
        items, (tp, tc, _) = self.compared_groups(scope, dim)
        ranked = sort_items(items, self.params.sort)
        wf = build_waterfall(items, tp, tc, self.top_n())
        return {
            "data": {
                "group_by": dim,
                "group_by_label": GROUP_BY_OPTIONS[dim],
                "next_level": NEXT_LEVEL.get(dim),
                "filter_param": FILTER_PARAM.get(dim),
                "totals": self.totals_out(scope, tp, tc),
                "waterfall": waterfall_out(wf),
                "groups": [item_out(i) for i in ranked[:MAX_GROUPS]],
                "group_count": len(items),
                "summary": self.change_summary(items, tp, tc),
            },
            "meta": self.meta(scope),
        }

    def change_summary(self, items: list[ComparedItem], tp: Decimal, tc: Decimal) -> dict[str, Any]:
        inc = [i for i in items if i.diff > 0]
        dec = [i for i in items if i.diff < 0]
        return {
            "increased_count": len(inc),
            "decreased_count": len(dec),
            "new_count": sum(1 for i in items if i.status == "new"),
            "removed_count": sum(1 for i in items if i.status == "removed"),
            "gross_increase": money(sum((i.diff for i in inc), ZERO)),
            "gross_decrease": money(sum((i.diff for i in dec), ZERO)),
            "net_change": money(tc - tp),
        }

    def contributors(self) -> dict[str, Any]:
        """Paged, sorted comparison rows (default: resources) for drill-down tables."""
        scope = self.scope()
        dim = self.params.group_by
        res_attrs = dim == "resource"
        items, (tp, tc, _) = self.compared_groups(scope, dim, resource_attributes=res_attrs)
        has_cmp = scope.comparison is not None
        ranked = sort_items(items, self.params.sort if has_cmp else "current_cost")
        p = self.params
        start = (p.page - 1) * p.page_size
        return {
            "data": [item_out(i, has_cmp) for i in ranked[start : start + p.page_size]],
            "meta": self.meta(
                scope,
                page=p.page,
                page_size=p.page_size,
                total=len(ranked),
                totals=self.totals_out(scope, tp, tc),
                group_by=dim,
                sort=p.sort,
            ),
        }

    def trend(self, *, include_budget: bool = True, include_forecast: bool = True) -> dict[str, Any]:
        from app.services import budget_service  # local import avoids a cycle

        scope = self.scope()
        series = self.series_payload(scope, None)
        budget_line = None
        forecast_line = None
        budget = budget_service.find_scope_budget(self.db, scope.filters, self.labels, scope.as_of) if include_budget else None
        g = self.params.granularity
        buckets = [date.fromisoformat(b) for b in series["buckets"]]
        if budget is not None:
            budget_line = []
            for b in buckets:
                if g == "monthly":
                    budget_line.append(money(budget_service.monthly_amount(budget, b)))
                elif g == "weekly":
                    budget_line.append(money(sum((budget_service.daily_amount(budget, b + timedelta(days=i)) for i in range(7)), ZERO)))
                else:
                    budget_line.append(money(budget_service.daily_amount(budget, b)))
        if include_forecast and g == "daily":
            from app.forecasting.forecast import forecast_period

            ms = P.month_start(scope.as_of)
            me = P.month_end(scope.as_of)
            if scope.current.period.end >= scope.as_of and scope.current.period.start <= me:
                method = settings_service.get_setting(self.db, "forecast.default_method")
                hist = self.repo.daily_totals(scope.filters, scope.as_of - timedelta(days=89), scope.as_of)
                fc = forecast_period(hist, as_of=scope.as_of, period_start=ms, period_end=me, method=method)
                forecast_line = {
                    "method": fc.method,
                    "method_label": fc.method_label,
                    "points": [{"date": d.isoformat(), "value": money(v)} for d, v in fc.projection],
                    "forecast_total": money(fc.forecast_total),
                    "period_start": ms.isoformat(),
                    "period_end": me.isoformat(),
                }
        return {
            "data": {
                **series,
                "budget": budget_line,
                "budget_name": budget.name if budget is not None else None,
                "forecast": forecast_line,
            },
            "meta": self.meta(scope),
        }

    # ------------------------------------------------------------------ KPIs --------
    def _kpi(self, f: CostFilters, key: str, title: str, cur: P.Period, prev: P.Period | None, spark: str, link: dict[str, str], note: str | None = None) -> dict[str, Any]:
        c = self.repo.total(f, cur)
        pv = self.repo.total(f, prev) if prev else None
        diff = c - pv if pv is not None else None
        return {
            "key": key,
            "title": title,
            "current": money(c),
            "previous": money(pv),
            "diff": money(diff),
            "pct": pct_out(pct_change(pv, c)) if pv is not None else None,
            "period": period_out(cur),
            "comparison_period": period_out(prev),
            "significance": self.significance(pv, c, diff) if pv is not None and diff is not None else None,
            "sparkline": spark,
            "link": link,
            "note": note,
            "kind": "actual",
        }

    def overview(self) -> dict[str, Any]:
        from app.forecasting.forecast import forecast_period
        from app.services import budget_service

        scope = self.scope()
        f = scope.filters
        a = scope.as_of
        ws = self.week_start
        today_label = "Today" if a == datetime.now(UTC).date() else f"Latest day ({a.strftime('%d %b')})"

        def rp(preset: str) -> P.ResolvedPeriod:
            return P.resolve_period(preset, a, week_start_isodow=ws)

        day = rp("today")
        yday = rp("yesterday")
        wtd = rp("week_to_date")
        pw = rp("previous_week")
        mtd = rp("month_to_date")
        pm = rp("previous_month")
        ytd = rp("year_to_date")
        l30 = rp("last_30_days")
        kpis = [
            self._kpi(f, "today", today_label, day.period, P.resolve_comparison(day, "previous_equivalent"), "daily", {"preset": "today"},
                      None if a == datetime.now(UTC).date() else "Billing data is not yet available for today; showing the latest available day."),
            self._kpi(f, "yesterday", "Previous day" if a != datetime.now(UTC).date() else "Yesterday", yday.period, P.resolve_comparison(yday, "previous_equivalent"), "daily", {"preset": "yesterday"}),
            self._kpi(f, "current_week", "Current week", wtd.period, P.resolve_comparison(wtd, "previous_equivalent"), "weekly", {"preset": "week_to_date"},
                      f"{wtd.elapsed_days} of 7 days; compared with the same days of the previous week" if wtd.is_incomplete else None),
            self._kpi(f, "previous_week", "Previous week", pw.period, P.resolve_comparison(pw, "previous_equivalent"), "weekly", {"preset": "previous_week"}),
            self._kpi(f, "current_month", "Current month", mtd.period, P.resolve_comparison(mtd, "previous_equivalent"), "monthly", {"preset": "month_to_date"},
                      f"{mtd.elapsed_days} of {mtd.nominal_days} days; compared with the same elapsed days" if mtd.is_incomplete else None),
            self._kpi(f, "previous_month", "Previous month", pm.period, P.resolve_comparison(pm, "previous_equivalent"), "monthly", {"preset": "previous_month"}),
            self._kpi(f, "year_to_date", "Year-to-date", ytd.period, P.resolve_comparison(ytd, "same_period_last_year"), "monthly", {"preset": "year_to_date", "comparison": "same_period_last_year"}),
        ]
        thirty = self._kpi(f, "change_30d", "30-day change", l30.period, P.resolve_comparison(l30, "previous_equivalent"), "daily", {"preset": "last_30_days"})
        thirty["display"] = "pct"

        # Budget & forecast (forecast is a projection, never an actual charge)
        method = settings_service.get_setting(self.db, "forecast.default_method")
        hist = self.repo.daily_totals(f, a - timedelta(days=89), a)
        fc = forecast_period(hist, as_of=a, period_start=mtd.period.start, period_end=mtd.nominal_end, method=method)
        budget = budget_service.find_scope_budget(self.db, f, self.labels, a)
        budget_amt = budget_service.monthly_amount(budget, a) if budget is not None else None
        prev_month_total = self.repo.total(f, pm.period)
        kpis.append({
            "key": "budget", "title": "Monthly budget", "kind": "budget",
            "current": money(budget_amt), "previous": money(fc.actual_to_date), "diff": None,
            "pct": pct_out(fc.actual_to_date / budget_amt * 100) if budget_amt else None,
            "period": period_out(P.Period(mtd.period.start, mtd.nominal_end)), "comparison_period": None,
            "note": (f"{budget.name}; {pct_out(fc.actual_to_date / budget_amt * 100) if budget_amt else 0}% consumed month-to-date" if budget is not None else "No budget configured for this scope"),
            "sparkline": None, "link": {"page": "budgets"}, "significance": None,
        })
        kpis.append({
            "key": "forecast", "title": "Forecast (month-end)", "kind": "forecast",
            "current": money(fc.forecast_total), "previous": money(prev_month_total), "diff": money(fc.forecast_total - prev_month_total),
            "pct": pct_out(pct_change(prev_month_total, fc.forecast_total)), "period": period_out(P.Period(mtd.period.start, mtd.nominal_end)),
            "comparison_period": period_out(pm.period), "note": f"Projection — {fc.method_label}. Not an actual charge.",
            "sparkline": None, "link": {"page": "budgets"}, "significance": None,
        })
        variance = (fc.forecast_total - budget_amt) if budget_amt is not None else None
        kpis.append({
            "key": "budget_variance", "title": "Forecast vs budget", "kind": "forecast",
            "current": money(variance), "previous": money(budget_amt), "diff": None,
            "pct": pct_out(variance / budget_amt * 100) if (variance is not None and budget_amt) else None,
            "period": period_out(P.Period(mtd.period.start, mtd.nominal_end)), "comparison_period": None,
            "note": ("Projected overspend" if variance and variance > 0 else "Projected underspend") if variance is not None else "No budget configured",
            "sparkline": None, "link": {"page": "budgets"}, "significance": ("notable_increase" if variance and variance > 0 else "normal") if variance is not None else None,
        })
        kpis.append(thirty)
        sav_q = select(func.count(), func.coalesce(func.sum(SavingsOpportunity.estimated_monthly_savings), 0)).where(
            SavingsOpportunity.status.in_(["open", "investigating", "accepted"]), SavingsOpportunity.billing_currency == scope.currency
        )
        if f.subscription_fks:
            sav_q = sav_q.where(SavingsOpportunity.subscription_fk.in_(f.subscription_fks))
        if f.application_ids:
            sav_q = sav_q.where(SavingsOpportunity.application_id.in_(f.application_ids))
        if f.environment_ids:
            sav_q = sav_q.where(SavingsOpportunity.environment_id.in_(f.environment_ids))
        if self.allowed is not None:
            sav_q = sav_q.where(SavingsOpportunity.subscription_fk.in_(list(self.allowed) or [-1]))
        cnt, est = self.db.execute(sav_q).one()
        kpis.append({
            "key": "savings", "title": "Potential savings", "kind": "estimate",
            "current": money(Decimal(est)), "previous": None, "diff": None, "pct": None, "period": None, "comparison_period": None,
            "note": f"{cnt} open opportunit{'y' if cnt == 1 else 'ies'}; estimated monthly, not realised",
            "sparkline": None, "link": {"page": "savings"}, "significance": None,
        })

        spark = {
            "daily": self._spark(f, P.Period(a - timedelta(days=29), a), "daily"),
            "weekly": self._spark(f, P.Period(P.week_start(a, ws) - timedelta(days=7 * 11), a), "weekly"),
            "monthly": self._spark(f, P.Period(P.add_months(P.month_start(a), -12), a), "monthly"),
        }
        return {"data": {"kpis": kpis, "sparklines": spark, "forecast_method": fc.method_label}, "meta": self.meta(scope)}

    def _spark(self, f: CostFilters, period: P.Period, g: str) -> list[dict[str, Any]]:
        rows = self.repo.series(f, period, g)
        vals = {r["bucket"]: Decimal(r["cost"]) for r in rows}
        return [{"bucket": b.isoformat(), "value": money(vals.get(b, ZERO))} for b in P.buckets(period, g, self.week_start)]


def subscription_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(AzureSubscription)).scalar_one()
