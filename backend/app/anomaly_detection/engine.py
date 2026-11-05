"""Anomaly detection engine (runs in the worker after each ingestion).

* Evaluates every enabled rule for each scope (subscription x service, resource,
  application x environment) over the last ``anomaly.lookback_days`` usage days.
* Idempotent: re-running over the same dates never creates duplicates.
* Episode merging: a spike that persists on consecutive days updates the existing open
  anomaly (occurrence_count, last_detected_date) instead of creating new ones, so the
  same unresolved issue does not raise repeated alerts.
* Evidence is computed from billing aggregates only. Explanations state measured facts;
  anything else is labelled as a hypothesis / suggested investigation step.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.comparison import ZERO, money, pct_out, qty, to_decimal
from app.analytics.periods import Period
from app.anomaly_detection import rules as R
from app.models import AnomalyEvent, AnomalyRule, AzureResource, CostAnomaly, DailyCostAggregate
from app.repositories.cost_repository import CostFilters, CostRepository
from app.services import settings_service
from app.services.labels import LabelResolver

log = logging.getLogger(__name__)

ACTIVE = ("open", "investigating", "acknowledged")
EPISODE_GAP_DAYS = 2
HISTORY_DAYS = 75


@dataclass
class ScopeSeries:
    key: str
    attrs: dict[str, Any]
    series: dict[date, Decimal]


def _fmt(v: Decimal | float | None, cur: str) -> str:
    if v is None:
        return "n/a"
    return f"{cur} {to_decimal(v):,.2f}"


class AnomalyEngine:
    def __init__(self, db: Session, dataset_type: str = "actual"):
        self.db = db
        self.dataset_type = dataset_type
        self.ws = settings_service.week_start(db)
        self.repo = CostRepository(db, self.ws)
        self.labels = LabelResolver(db)
        self.sensitivity = settings_service.get_setting(db, "anomaly.sensitivity")
        self.severity_thresholds = settings_service.get_setting(db, "anomaly.severity_thresholds")
        self.exclude_charge_types = settings_service.get_setting(db, "anomaly.exclude_charge_types")
        self._series_cache: dict[tuple[str, str], list[ScopeSeries]] = {}

    # --------------------------------------------------------------------------------
    def run(self, *, start: date | None = None, end: date | None = None, lookback_days: int | None = None) -> dict[str, Any]:
        rules = list(self.db.execute(select(AnomalyRule).where(AnomalyRule.enabled.is_(True)).order_by(AnomalyRule.id)).scalars())
        t = DailyCostAggregate.__table__
        currencies = [r[0] for r in self.db.execute(select(t.c.billing_currency).where(t.c.dataset_type == self.dataset_type).distinct())]
        stats = {"created": 0, "updated": 0, "skipped_existing": 0, "new_anomaly_ids": [], "evaluated_rules": len(rules)}
        lookback = lookback_days or int(settings_service.get_setting(self.db, "anomaly.lookback_days"))
        for currency in currencies:
            f = CostFilters(dataset_type=self.dataset_type, currency=currency, exclude_charge_types=self.exclude_charge_types or None)
            _, data_end = self.repo.date_bounds(f)
            if data_end is None:
                continue
            end_d = min(end or data_end, data_end)
            start_d = start or (end_d - timedelta(days=lookback - 1))
            self._series_cache.clear()
            for rule in rules:
                try:
                    self._run_rule(rule, f, currency, start_d, end_d, stats)
                except Exception:  # noqa: BLE001 -- one bad rule must not stop the others
                    log.exception("Anomaly rule failed", extra={"rule": rule.code})
            self.db.flush()
        return stats

    # --------------------------------------------------------------------------------
    def _scopes(self, level: str, f: CostFilters, start: date, end: date) -> list[ScopeSeries]:
        ck = (level, f.currency or "")
        if ck in self._series_cache:
            return self._series_cache[ck]
        period = Period(start - timedelta(days=HISTORY_DAYS), end)
        out: dict[str, ScopeSeries] = {}
        if level == "subscription_service":
            for r in self.repo.series(f, period, "daily", ["subscription", "service_category"]):
                sub = self.labels.subs.get(r["subscription_fk"])
                key = f"{r['subscription_fk']}:{r['service_category']}"
                s = out.setdefault(key, ScopeSeries(key, {
                    "subscription_fk": r["subscription_fk"],
                    "service_category": r["service_category"],
                    "application_id": sub.application_id if sub else None,
                    "environment_id": sub.environment_id if sub else None,
                }, {}))
                s.series[r["bucket"]] = s.series.get(r["bucket"], ZERO) + Decimal(r["cost"])
        elif level == "application_environment":
            for r in self.repo.series(f, period, "daily", ["application", "environment"]):
                key = f"{r['application_id']}:{r['allocation_status']}:{r['environment_id']}"
                s = out.setdefault(key, ScopeSeries(key, {
                    "application_id": r["application_id"],
                    "allocation_status": r["allocation_status"],
                    "environment_id": r["environment_id"],
                }, {}))
                s.series[r["bucket"]] = s.series.get(r["bucket"], ZERO) + Decimal(r["cost"])
        elif level == "subscription":
            for r in self.repo.series(f, period, "daily", ["subscription"]):
                sub = self.labels.subs.get(r["subscription_fk"])
                key = str(r["subscription_fk"])
                s = out.setdefault(key, ScopeSeries(key, {"subscription_fk": r["subscription_fk"],
                                                          "application_id": sub.application_id if sub else None,
                                                          "environment_id": sub.environment_id if sub else None}, {}))
                s.series[r["bucket"]] = s.series.get(r["bucket"], ZERO) + Decimal(r["cost"])
        elif level == "resource":
            attrs_rows = self.repo.grouped_compare(f, period, None, ["resource"], resource_attributes=True)
            attrs = {r.values["resource_key"]: {**r.extra, "resource_key": r.values["resource_key"], "resource_name": r.label_hint} for r in attrs_rows if r.values["resource_key"]}
            for r in self.repo.series(f, period, "daily", ["resource"]):
                k = r["resource_key"]
                if not k:
                    continue
                s = out.setdefault(k, ScopeSeries(k, attrs.get(k, {"resource_key": k}), {}))
                s.series[r["bucket"]] = s.series.get(r["bucket"], ZERO) + Decimal(r["cost"])
        else:
            raise ValueError(f"Unknown scope level {level}")
        result = list(out.values())
        self._series_cache[ck] = result
        return result

    def _passes(self, rule: AnomalyRule, attrs: dict[str, Any]) -> bool:
        flt = rule.filters or {}
        groups = flt.get("environment_groups")
        if groups:
            env = self.labels.envs.get(attrs.get("environment_id"))
            if env is None or env.environment_group not in groups:
                return False
        cats = flt.get("service_categories")
        if cats and attrs.get("service_category") not in cats:
            return False
        excl = flt.get("exclude_service_categories")
        if excl and attrs.get("service_category") in excl:
            return False
        return True

    def _params(self, rule: AnomalyRule, attrs: dict[str, Any]) -> dict[str, Any]:
        p = dict(rule.params or {})
        ov = (p.pop("category_overrides", None) or {}).get(attrs.get("service_category") or "", {})
        p.update(ov)
        for k in ("pct_threshold", "min_abs", "min_daily_cost"):
            if k in p:
                p[k] = R.scaled(p[k], self.sensitivity)
        return p

    # --------------------------------------------------------------------------------
    def _run_rule(self, rule: AnomalyRule, f: CostFilters, currency: str, start: date, end: date, stats: dict[str, Any]) -> None:
        if rule.detection_type == "new_resource":
            self._run_new_resource(rule, f, currency, start, end, stats)
            return
        for sc in self._scopes(rule.scope_level, f, start, end):
            if not self._passes(rule, sc.attrs):
                continue
            p = self._params(rule, sc.attrs)
            d = start
            while d <= end:
                det = self._detect(rule.detection_type, sc.series, d, p)
                if det is not None:
                    self._upsert(rule, sc, det, d, f, currency, p, stats)
                d += timedelta(days=1)

    def _detect(self, dtype: str, series: dict[date, Decimal], d: date, p: dict[str, Any]) -> R.Detection | None:
        if dtype == "daily_spike":
            return R.detect_daily_spike(series, d, method=p.get("method", "same_weekday_median"), window=int(p.get("window", 4)),
                                        pct_threshold=p.get("pct_threshold", 25), min_abs=p.get("min_abs", 200),
                                        min_history_days=int(p.get("min_history_days", 14)))
        if dtype == "weekly_spike":
            return R.detect_weekly_spike(series, d, weeks=int(p.get("weeks", 4)), pct_threshold=p.get("pct_threshold", 15), min_abs=p.get("min_abs", 750))
        if dtype == "monthly_spike":
            return R.detect_monthly_spike(series, d, pct_threshold=p.get("pct_threshold", 15), min_abs=p.get("min_abs", 2000),
                                          min_elapsed_days=int(p.get("min_elapsed_days", 5)))
        if dtype == "continuous_increase":
            return R.detect_continuous_increase(series, d, weeks=int(p.get("weeks", 4)), min_step_pct=p.get("min_step_pct", 3), min_abs=p.get("min_abs", 300))
        raise ValueError(f"Unknown detection type {dtype}")

    def _run_new_resource(self, rule: AnomalyRule, f: CostFilters, currency: str, start: date, end: date, stats: dict[str, Any]) -> None:
        p = self._params(rule, {})
        lookback = int(p.get("lookback_days", 7))
        threshold = to_decimal(p.get("min_daily_cost", 50))
        scopes = {s.key: s for s in self._scopes("resource", f, start, end)}
        new_res = self.db.execute(
            select(AzureResource).where(AzureResource.first_seen_date >= start - timedelta(days=lookback), AzureResource.first_seen_date <= end)
        ).scalars()
        for res in new_res:
            sc = scopes.get(res.resource_key)
            if sc is None or not self._passes(rule, sc.attrs):
                continue
            first = res.first_seen_date
            # no billing records before first_seen in the history window -> genuinely new
            if any(d < first and v != ZERO for d, v in sc.series.items()):
                continue
            days = [first + timedelta(days=i) for i in range((end - first).days + 1)]
            total = sum((sc.series.get(d, ZERO) for d in days), ZERO)
            avg = total / Decimal(len(days)) if days else ZERO
            if avg < threshold:
                continue
            det = R.Detection(observed=total, baseline=ZERO, previous=ZERO, period_start=first, period_end=end, baseline_method="none",
                              baseline_window=0, baseline_points=[], extra={"avg_daily_cost": str(avg), "projected_monthly_cost": str(avg * 30), "days_billed": len(days)})
            self._upsert(rule, sc, det, end, f, currency, p, stats, severity_basis=avg * 30)

    # --------------------------------------------------------------------------------
    def _scope_filters(self, rule: AnomalyRule, sc: ScopeSeries, f: CostFilters) -> CostFilters:
        g = CostFilters(**{**f.__dict__})
        a = sc.attrs
        if rule.scope_level == "resource":
            g.resource_keys = [sc.key]
        if rule.scope_level in ("subscription_service", "subscription"):
            g.subscription_fks = [a["subscription_fk"]]
        if rule.scope_level == "subscription_service":
            g.service_categories = [a["service_category"]]
        if rule.scope_level == "application_environment":
            if a.get("application_id") is not None:
                g.application_ids = [a["application_id"]]
            else:
                g.allocation_statuses = [a.get("allocation_status") or "unallocated"]
            g.environment_ids = [a["environment_id"]] if a.get("environment_id") is not None else [-1]
        return g

    @staticmethod
    def _windows(det: R.Detection) -> list[list[date]]:
        out = []
        for label, _ in det.baseline_points:
            if "/" in label:
                a, b = label.split("/")
                s, e = date.fromisoformat(a), date.fromisoformat(b)
                out.append([s + timedelta(days=i) for i in range((e - s).days + 1)])
            else:
                out.append([date.fromisoformat(label)])
        return out

    def _evidence(self, rule: AnomalyRule, sc: ScopeSeries, det: R.Detection, f: CostFilters) -> dict[str, Any]:
        g = self._scope_filters(rule, sc, f)
        windows = self._windows(det)
        lo = min([det.period_start] + [w[0] for w in windows]) if windows else det.period_start
        observed_days = [det.period_start + timedelta(days=i) for i in range((det.period_end - det.period_start).days + 1)]

        def breakdown(dims: list[str], with_qty: bool):
            rows = self.repo.series(g, Period(lo, det.period_end), "daily", dims, with_quantity=with_qty)
            agg: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"daily": defaultdict(lambda: ZERO), "qty": defaultdict(lambda: ZERO)})
            for r in rows:
                key = tuple(r.get(c) for c in self._cols(dims))
                agg[key]["daily"][r["bucket"]] += Decimal(r["cost"])
                if with_qty:
                    agg[key]["qty"][r["bucket"]] += Decimal(r.get("quantity") or 0)
            out = []
            for key, v in agg.items():
                obs = sum((v["daily"][d] for d in observed_days), ZERO)
                obs_q = sum((v["qty"][d] for d in observed_days), ZERO)
                if windows:
                    base = sum((sum((v["daily"][d] for d in w), ZERO) for w in windows), ZERO) / Decimal(len(windows))
                    base_q = sum((sum((v["qty"][d] for d in w), ZERO) for w in windows), ZERO) / Decimal(len(windows))
                else:
                    base, base_q = ZERO, ZERO
                out.append((key, obs, base, obs_q, base_q))
            out.sort(key=lambda x: -abs(x[1] - x[2]))
            return out[:8]

        meters = [
            {"meter_category": k[0], "meter_name": k[1], "unit": k[2], "observed_cost": money(o), "baseline_cost": money(b), "diff": money(o - b),
             "observed_quantity": qty(oq), "baseline_quantity": qty(bq), "quantity_diff": qty(oq - bq)}
            for k, o, b, oq, bq in breakdown(["meter_category", "meter_name", "unit"], True)
        ]
        resources = []
        if rule.scope_level != "resource":
            res_rows = breakdown(["resource"], False)
            names = {r.resource_key: r.resource_name for r in self.db.execute(select(AzureResource).where(AzureResource.resource_key.in_([k[0] for k, *_ in res_rows if k[0]]))).scalars()}
            resources = [
                {"resource_key": k[0], "resource_name": names.get(k[0]) or (k[0].rsplit("/", 1)[-1] if k[0] else "(non-resource charges)"),
                 "resource_id": None, "observed_cost": money(o), "baseline_cost": money(b), "diff": money(o - b)}
                for k, o, b, _, _ in res_rows
            ]
            ids = {r.resource_key: r.id for r in self.db.execute(select(AzureResource).where(AzureResource.resource_key.in_([x["resource_key"] for x in resources if x["resource_key"]]))).scalars()}
            for x in resources:
                x["resource_id"] = ids.get(x["resource_key"])
        hist_start = det.period_end - timedelta(days=41)
        history = [{"date": (hist_start + timedelta(days=i)).isoformat(), "cost": money(sc.series.get(hist_start + timedelta(days=i), ZERO))} for i in range(42)]
        return {
            "baseline_method": det.baseline_method,
            "baseline_description": det.baseline_description,
            "baseline_points": [{"period": lbl, "cost": money(v)} for lbl, v in det.baseline_points],
            "observed": money(det.observed),
            "baseline": money(det.baseline),
            "observed_period": {"start": det.period_start.isoformat(), "end": det.period_end.isoformat()},
            "rule": {"code": rule.code, "name": rule.name, "detection_type": rule.detection_type, "params": rule.params, "sensitivity": self.sensitivity},
            "top_meters": meters,
            "top_resources": resources,
            "history": history,
            "extra": det.extra,
        }

    @staticmethod
    def _cols(dims: list[str]) -> list[str]:
        from app.repositories.cost_repository import DIM_COLUMNS

        out: list[str] = []
        for d in dims:
            out.extend(DIM_COLUMNS[d])
        return out

    def _scope_is_demo(self, sc: ScopeSeries) -> bool:
        sub_fk = sc.attrs.get("subscription_fk")
        if sub_fk is not None and sub_fk in self.labels.subs:
            return self.labels.subs[sub_fk].is_demo
        return any(s.is_demo for s in self.labels.subs.values())

    def _describe_scope(self, rule: AnomalyRule, sc: ScopeSeries) -> tuple[str, str]:
        a = sc.attrs
        sub = self.labels.subs.get(a.get("subscription_fk")) if a.get("subscription_fk") is not None else None
        if rule.scope_level == "resource":
            return a.get("resource_name") or sc.key.rsplit("/", 1)[-1], a.get("service_category") or "Other Services"
        if rule.scope_level == "subscription_service":
            return f"{a['service_category']} in {sub.subscription_name if sub else a.get('subscription_fk')}", a["service_category"]
        if rule.scope_level == "application_environment":
            _, app = self.labels.application(a.get("application_id"), a.get("allocation_status"))
            _, env = self.labels.environment(a.get("environment_id"))
            return f"{app} · {env}", "Non-Production" if (self.labels.envs.get(a.get("environment_id")) and self.labels.envs[a["environment_id"]].environment_group == "non_production") else "Total"
        return sub.subscription_name if sub else str(a.get("subscription_fk")), "Total"

    def _upsert(self, rule: AnomalyRule, sc: ScopeSeries, det: R.Detection, target: date, f: CostFilters, currency: str,
                params: dict[str, Any], stats: dict[str, Any], severity_basis: Decimal | None = None) -> None:
        scope_key = f"{rule.scope_level}:{sc.key}"
        existing = self.db.execute(
            select(CostAnomaly)
            .where(CostAnomaly.rule_code == rule.code, CostAnomaly.scope_key == scope_key, CostAnomaly.billing_currency == currency,
                   CostAnomaly.dataset_type == self.dataset_type)
            .order_by(CostAnomaly.last_detected_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing and existing.detection_date <= target <= existing.last_detected_date:
            stats["skipped_existing"] += 1
            return
        abs_inc = severity_basis if severity_basis is not None else det.abs_increase
        severity = R.classify_severity(abs_inc, det.pct_increase, self.severity_thresholds, self.sensitivity)
        if existing and existing.status in ACTIVE and target > existing.last_detected_date and (target - existing.last_detected_date).days <= EPISODE_GAP_DAYS:
            existing.last_detected_date = target
            existing.occurrence_count += 1
            existing.period_end = max(existing.period_end, det.period_end)
            if det.abs_increase > existing.absolute_increase:
                self._fill(existing, rule, sc, det, f, currency, params)
            if R.SEVERITY_RANK[severity] > R.SEVERITY_RANK.get(existing.severity, 0):
                existing.severity = severity
            self.db.add(AnomalyEvent(anomaly_id=existing.id, event_type="redetected", actor="system",
                                     details={"date": target.isoformat(), "observed": money(det.observed), "baseline": money(det.baseline)}))
            stats["updated"] += 1
            return
        a = CostAnomaly(rule_id=rule.id, rule_code=rule.code, detection_type=rule.detection_type, scope_level=rule.scope_level,
                        scope_key=scope_key, detection_date=target, last_detected_date=target, dataset_type=self.dataset_type,
                        billing_currency=currency, severity=severity, status="open", occurrence_count=1,
                        is_demo=self._scope_is_demo(sc))
        self._fill(a, rule, sc, det, f, currency, params)
        self.db.add(a)
        self.db.flush()
        self.db.add(AnomalyEvent(anomaly_id=a.id, event_type="detected", actor="system", to_status="open",
                                 details={"date": target.isoformat(), "rule": rule.code}))
        stats["created"] += 1
        stats["new_anomaly_ids"].append(a.id)

    def _fill(self, a: CostAnomaly, rule: AnomalyRule, sc: ScopeSeries, det: R.Detection, f: CostFilters, currency: str, params: dict[str, Any]) -> None:
        name, category = self._describe_scope(rule, sc)
        attrs = sc.attrs
        a.category = category
        titles = {
            "daily_spike": "Daily cost spike",
            "weekly_spike": "Weekly cost increase",
            "monthly_spike": "Monthly cost increase",
            "new_resource": "New expensive resource",
            "continuous_increase": "Continuous cost increase",
        }
        a.title = f"{titles.get(rule.detection_type, rule.name)} — {name}"
        a.period_start, a.period_end = det.period_start, det.period_end
        a.subscription_fk = attrs.get("subscription_fk")
        a.application_id = attrs.get("application_id")
        a.environment_id = attrs.get("environment_id")
        a.service_category = attrs.get("service_category")
        a.resource_group = attrs.get("resource_group")
        a.resource_key = attrs.get("resource_key") if rule.scope_level == "resource" else None
        a.resource_name = attrs.get("resource_name") if rule.scope_level == "resource" else None
        a.previous_cost = det.previous
        a.current_cost = det.observed
        a.expected_baseline = det.baseline
        a.absolute_increase = det.abs_increase
        a.percentage_increase = det.pct_increase
        evidence = self._evidence(rule, sc, det, f)
        evidence["thresholds_applied"] = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in params.items()}
        a.evidence = evidence
        a.explanation = self._explain(rule, det, evidence, currency, name)
        steps = list(R.RECOMMENDED_STEPS.get(a.service_category or "", R.RECOMMENDED_STEPS["_default"]))
        env = self.labels.envs.get(a.environment_id) if a.environment_id is not None else None
        if env is not None and env.environment_group == "non_production":
            steps += R.RECOMMENDED_STEPS["_non_production"]
        if rule.detection_type == "new_resource":
            steps = R.RECOMMENDED_STEPS["_new_resource"] + steps[:2]
        a.recommended_steps = steps
        a.updated_at = datetime.now(UTC)

    def _explain(self, rule: AnomalyRule, det: R.Detection, ev: dict[str, Any], cur: str, name: str) -> str:
        period = det.period_start.isoformat() if det.period_start == det.period_end else f"{det.period_start.isoformat()} to {det.period_end.isoformat()}"
        if rule.detection_type == "new_resource":
            x = det.extra
            text = (f"'{name}' first appeared in billing on {det.period_start.isoformat()} and has been billed {x['days_billed']} day(s), "
                    f"totalling {_fmt(det.observed, cur)} (average {_fmt(to_decimal(x['avg_daily_cost']), cur)}/day; "
                    f"≈ {_fmt(to_decimal(x['projected_monthly_cost']), cur)} per 30 days if usage continues). No billing records exist for it before that date.")
        else:
            pct = det.pct_increase
            text = (f"Cost for {period} was {_fmt(det.observed, cur)} against an expected baseline of {_fmt(det.baseline, cur)} "
                    f"({det.baseline_description}): an increase of {_fmt(det.abs_increase, cur)}"
                    + (f" ({pct_out(pct):+.1f}%)." if pct is not None else "."))
        meters = [m for m in ev.get("top_meters", []) if m["diff"]]
        if meters:
            m = meters[0]
            text += f" Largest contributing meter: '{m['meter_name']}' ({'+' if m['diff'] >= 0 else ''}{m['diff']:,.2f}"
            if m.get("unit") and m.get("baseline_quantity") is not None:
                text += f"; quantity {m['baseline_quantity']:,.2f} → {m['observed_quantity']:,.2f} {m['unit']}"
            text += ")."
        res = [r for r in ev.get("top_resources", []) if r["diff"]]
        if res:
            text += f" Largest contributing resource: '{res[0]['resource_name']}' ({'+' if res[0]['diff'] >= 0 else ''}{res[0]['diff']:,.2f})."
        return text
