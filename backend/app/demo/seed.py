"""Seed DEMO DATA end to end through the real ingestion pipeline."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text

from app.analytics.periods import Period, add_months, month_end, month_start
from app.core.config import get_settings
from app.core.db import session_factory, session_scope
from app.demo.catalog import APPLICATIONS, DEMO_TENANT, SUBSCRIPTIONS
from app.demo.generator import CONTAINER, demo_window, generate_demo_exports
from app.models import (
    Application,
    ApplicationMapping,
    AzureSubscription,
    Budget,
    Environment,
    SavingsOpportunity,
)
from app.repositories.cost_repository import CostFilters, CostRepository
from app.services import settings_service
from app.services.analytics_runner import run_analytics
from app.services.subscription_service import upsert_subscription

log = logging.getLogger(__name__)


def demo_present(db) -> bool:
    return db.execute(select(AzureSubscription.id).where(AzureSubscription.is_demo.is_(True)).limit(1)).first() is not None


def register_demo_configuration(db) -> None:
    for code, name, desc, sort in APPLICATIONS:
        app = db.execute(select(Application).where(Application.code == code)).scalar_one_or_none()
        if app is None:
            db.add(Application(code=code, name=name, description=desc, sort_order=sort, is_demo=True))
    db.flush()
    for _idx, app, env, guid, name, _region in SUBSCRIPTIONS:
        ds_defs = [
            {"dataset_type": ds, "export_name": f"acip-{ds}-daily", "container": CONTAINER, "root_folder_path": f"demo/{guid}/{ds}", "storage_account_url": "local://demo"}
            for ds in ("actual", "amortized")
        ]
        upsert_subscription(db, {"subscription_id": guid, "subscription_name": name, "application": app, "environment": env,
                                 "tenant_id": DEMO_TENANT, "billing_currency": "USD", "enabled": True, "is_demo": True, "exports": ds_defs})
    envs = {e.code: e.id for e in db.execute(select(Environment)).scalars()}
    sub1 = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == SUBSCRIPTIONS[0][3])).scalar_one()
    if not db.execute(select(ApplicationMapping).where(ApplicationMapping.pattern == "rg-hub-network")).first():
        db.add(ApplicationMapping(match_type="resource_group", pattern="rg-hub-network", subscription_fk=sub1.id, application_id=None,
                                  environment_id=envs["shared"], allocation_status="shared", priority=10,
                                  description="DEMO: hub network is shared infrastructure billed centrally in the App1 production subscription"))
    if not db.execute(select(ApplicationMapping).where(ApplicationMapping.pattern == "rg-sandbox-*")).first():
        db.add(ApplicationMapping(match_type="resource_group", pattern="rg-sandbox-*", application_id=None, environment_id=envs["unallocated"],
                                  allocation_status="unallocated", priority=20, description="DEMO: sandbox resources pending owner confirmation"))
    db.flush()


def _round_up(v: Decimal, step: int = 1000) -> Decimal:
    return Decimal(math.ceil(float(v) / step) * step)


def create_demo_budgets(db) -> int:
    if db.execute(select(Budget.id).limit(1)).first():
        return 0
    repo = CostRepository(db, settings_service.week_start(db))
    base = CostFilters(dataset_type="actual", currency="USD")
    _, as_of = repo.date_bounds(base)
    pm_start = month_start(add_months(month_start(as_of), -1))
    pm = Period(pm_start, month_end(pm_start))
    start = date(as_of.year, 1, 1)
    total = repo.total(base, pm)
    envs = {e.code: e for e in db.execute(select(Environment)).scalars()}
    budgets: list[Budget] = [
        Budget(name="Total Azure — monthly", scope_type="total", scope_ref=None, period_type="monthly", amount=_round_up(total * Decimal("1.02")),
               currency="USD", cost_type="actual", start_date=start, thresholds=[70, 80, 90, 100], is_demo=True, created_by="demo-seed",
               notes="DEMO budget derived from synthetic data"),
        Budget(name="Total Azure — annual", scope_type="total", scope_ref=None, period_type="annual", amount=_round_up(total * 12 * Decimal("1.05"), 10000),
               currency="USD", cost_type="actual", start_date=start, thresholds=[70, 80, 90, 100], is_demo=True, created_by="demo-seed"),
    ]
    for app in db.execute(select(Application).order_by(Application.sort_order)).scalars():
        t = repo.total(CostFilters(dataset_type="actual", currency="USD", application_ids=[app.id]), pm)
        factor = Decimal("0.98") if app.code == "app1" else Decimal("1.06")
        budgets.append(Budget(name=f"{app.name} — monthly", scope_type="application", scope_ref=str(app.id), period_type="monthly",
                              amount=_round_up(t * factor, 500), currency="USD", cost_type="actual", start_date=start, is_demo=True, created_by="demo-seed"))
    for group, name, factor in (("production", "Production", Decimal("1.03")), ("non_production", "Non-Production", Decimal("1.05"))):
        ids = [e.id for e in envs.values() if e.environment_group == group]
        t = repo.total(CostFilters(dataset_type="actual", currency="USD", environment_ids=ids), pm)
        budgets.append(Budget(name=f"{name} — monthly", scope_type="environment", scope_ref=group, period_type="monthly",
                              amount=_round_up(t * factor, 500), currency="USD", cost_type="actual", start_date=start, is_demo=True, created_by="demo-seed"))
    sub4 = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == SUBSCRIPTIONS[3][3])).scalar_one()
    t = repo.total(CostFilters(dataset_type="actual", currency="USD", subscription_fks=[sub4.id]), pm)
    budgets.append(Budget(name=f"{sub4.subscription_name} — monthly", scope_type="subscription", scope_ref=sub4.subscription_id, period_type="monthly",
                          amount=_round_up(t * Decimal("0.90"), 100), currency="USD", cost_type="actual", start_date=start, is_demo=True, created_by="demo-seed",
                          notes="DEMO: deliberately tight budget to demonstrate threshold alerts"))
    for b in budgets:
        db.add(b)
    db.flush()
    return len(budgets)


def create_demo_advisor_recommendations(db) -> int:
    from app.models import AzureResource

    samples = [
        ("vm-app3-prod-batch01", "Right-size or shut down underutilized virtual machine", Decimal("2950.00"), Decimal("1475.00"),
         "Average CPU utilisation below 5% and network below 2% over the last 7 days (Advisor criteria).",
         "Resize to a smaller SKU (e.g. Standard_D8s_v5) or deallocate outside batch windows.", {"avg_cpu_pct_7d": 3.4, "recommended_sku": "Standard_D8s_v5"}),
        ("aks-userpool-27182818-vmss", "Buy reserved instances to save over pay-as-you-go costs", Decimal("52000.00"), Decimal("11200.00"),
         "Consistent Standard_E16s_v5 usage over the last 30 days suitable for a 1-year reservation (Advisor look-back analysis).",
         "Evaluate a 1-year reservation or compute savings plan for the steady baseline of the node pool.", {"term": "P1Y", "lookback_days": 30, "recommended_quantity": 50}),
        ("log-app3-prod", "Consider Basic Logs for verbose tables", Decimal("6100.00"), Decimal("900.00"),
         "High-volume tables (ContainerLogV2) are queried rarely; Basic Logs ingestion is cheaper.",
         "Move rarely-queried verbose tables to the Basic Logs plan and review retention.", {"tables": ["ContainerLogV2", "AppTraces"]}),
    ]
    n = 0
    for name, title, monthly_cost, savings, issue, rec, ext in samples:
        res = db.execute(select(AzureResource).where(AzureResource.resource_name == name)).scalars().first()
        if res is None:
            continue
        key = f"ADVISOR_DEMO:{res.resource_key}"
        if db.execute(select(SavingsOpportunity.id).where(SavingsOpportunity.opportunity_key == key)).first():
            continue
        db.add(SavingsOpportunity(
            opportunity_key=key, rule_code="AZURE_ADVISOR", title=f"{title}: {name}", resource_key=res.resource_key, resource_name=name,
            subscription_fk=res.subscription_fk, application_id=res.application_id, environment_id=res.environment_id,
            service_category=res.service_category, billing_currency="USD", current_monthly_cost=monthly_cost, estimated_monthly_savings=savings,
            savings_basis="Savings amount as reported by the (DEMO sample) Advisor recommendation.", issue=issue,
            evidence={"source": "DEMO sample modelled on an Azure Advisor cost recommendation — not a real Advisor result", **ext},
            recommendation=rec, evidence_source="azure_advisor", status="open", is_demo=True,
        ))
        n += 1
    db.flush()
    return n


def seed_demo(force_regenerate: bool = False) -> dict[str, Any]:
    from worker.ingestion.pipeline import IngestionFailure, sync_subscription

    settings = get_settings()
    with session_scope() as db:
        register_demo_configuration(db)
        ws = settings_service.week_start(db)
    summary = generate_demo_exports(settings.local_export_root, week_start_isodow=ws)
    log.info("Demo export files generated", extra={k: v for k, v in summary.items() if k != "definitions"})
    sf = session_factory()
    results = []
    with session_scope() as db:
        sub_ids = [s.id for s in db.execute(select(AzureSubscription).where(AzureSubscription.is_demo.is_(True)).order_by(AzureSubscription.id)).scalars()]
    for sid in sub_ids:
        try:
            results.append(sync_subscription(sf, sid, force=force_regenerate))
        except IngestionFailure as exc:
            results.append({"subscription_fk": sid, "error": str(exc), **exc.details})
    with session_scope() as db:
        budgets = create_demo_budgets(db)
        advisor = create_demo_advisor_recommendations(db)
    with session_scope() as db:
        analytics = run_analytics(db, lookback_days=60)
    return {"generation": {k: v for k, v in summary.items() if k != "definitions"}, "ingestion": results, "budgets": budgets,
            "advisor_samples": advisor, "analytics": analytics, "window": demo_window(week_start_isodow=ws).__dict__}


def reset_demo() -> dict[str, Any]:
    """Remove all demo subscriptions and their data (configuration seeds remain)."""
    import shutil
    from pathlib import Path

    with session_scope() as db:
        subs = list(db.execute(select(AzureSubscription).where(AzureSubscription.is_demo.is_(True))).scalars())
        ids = [s.id for s in subs]
        if ids:
            for table in ("cost_records", "cost_records_staging", "daily_cost_aggregates", "monthly_cost_aggregates", "resource_cost_aggregates",
                          "meter_cost_aggregates", "cost_data_slices", "azure_resources", "resource_groups"):
                db.execute(text(f"DELETE FROM {table} WHERE subscription_fk = ANY(:ids)"), {"ids": ids})
            db.execute(text("DELETE FROM cost_anomalies WHERE is_demo"))
            db.execute(text("DELETE FROM savings_opportunities WHERE is_demo"))
            db.execute(text("DELETE FROM notification_history WHERE is_demo"))
            db.execute(delete(Budget).where(Budget.is_demo.is_(True)))
            db.execute(text("DELETE FROM application_mappings WHERE description LIKE 'DEMO:%'"))
            for s in subs:
                db.delete(s)
            db.execute(delete(Application).where(Application.is_demo.is_(True)))
    shutil.rmtree(Path(get_settings().local_export_root) / CONTAINER / "demo", ignore_errors=True)
    return {"removed_subscriptions": len(ids), "at": datetime.now(UTC).isoformat()}
