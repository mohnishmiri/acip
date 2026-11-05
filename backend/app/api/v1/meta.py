from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.allocation import SERVICE_CATEGORIES
from app.analytics.periods import COMPARISON_MODES, PRESETS
from app.core.config import APP_VERSION, get_settings
from app.core.db import get_db
from app.models import Application, AzureSubscription, Environment
from app.repositories.cost_repository import GROUP_BY_OPTIONS, CostFilters, CostRepository
from app.security.auth import CurrentUser, get_current_user, require
from app.services import freshness_service, settings_service

router = APIRouter(prefix="/meta", tags=["Metadata"])


@router.get("/client-config", summary="Public runtime configuration for the SPA (no secrets)")
def client_config():
    s = get_settings()
    return {
        "app_name": s.app_name,
        "version": APP_VERSION,
        "environment": s.app_env,
        "auth_mode": s.app_auth_mode,
        "entra": {
            "tenant_id": s.entra_tenant_id,
            "client_id": s.entra_spa_client_id,
            "authority": f"{s.entra_authority_host}/{s.entra_tenant_id}" if s.entra_tenant_id else None,
            "api_scope": s.entra_api_scope,
        } if s.app_auth_mode == "entra" else None,
        "demo_mode": s.demo_mode,
        "azure_integration": s.azure_auth_mode != "disabled",
    }


@router.get("/me", summary="Current user, roles and permissions")
def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "name": user.name,
        "email": user.email,
        "roles": sorted(user.roles),
        "primary_role": user.primary_role,
        "permissions": sorted(user.permissions),
        "auth_mode": user.auth_mode,
        "scoped_application_ids": sorted(user.scoped_application_ids) if user.scoped_application_ids is not None else None,
    }


@router.get("/filters", summary="Filter options (applications, environments, subscriptions, dimensions)")
def filters(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    allowed = user.allowed_subscription_fks
    subs = [s for s in db.execute(select(AzureSubscription).order_by(AzureSubscription.id)).scalars() if allowed is None or s.id in allowed]
    app_ids = {s.application_id for s in subs}
    apps = [a for a in db.execute(select(Application).order_by(Application.sort_order, Application.name)).scalars()
            if user.scoped_application_ids is None or a.id in user.scoped_application_ids]
    envs = list(db.execute(select(Environment).order_by(Environment.sort_order)).scalars())
    repo = CostRepository(db, settings_service.week_start(db))
    base = CostFilters(dataset_type="actual", allowed_subscription_fks=allowed)
    return {
        "applications": [{"id": a.id, "code": a.code, "name": a.name, "is_demo": a.is_demo, "has_subscriptions": a.id in app_ids} for a in apps],
        "environments": [{"code": e.code, "name": e.name, "group": e.environment_group, "is_production": e.is_production} for e in envs],
        "environment_groups": [
            {"code": "production", "name": "Production"},
            {"code": "non_production", "name": "Non-Production"},
            {"code": "shared", "name": "Shared Services"},
            {"code": "unallocated", "name": "Unallocated"},
        ],
        "subscriptions": [
            {"subscription_id": s.subscription_id, "subscription_name": s.subscription_name, "application_id": s.application_id,
             "environment": next((e.code for e in envs if e.id == s.environment_id), None), "billing_currency": s.billing_currency,
             "enabled": s.enabled, "is_demo": s.is_demo}
            for s in subs
        ],
        "service_categories": sorted(set(SERVICE_CATEGORIES) | set(repo.distinct_values("service_category", base))),
        "regions": repo.distinct_values("region", base),
        "currencies": repo.distinct_values("billing_currency", base),
        "charge_types": repo.distinct_values("charge_type", base),
        "pricing_models": repo.distinct_values("pricing_model", base),
        "owners": repo.distinct_values("owner", base),
        "cost_centers": repo.distinct_values("cost_center", base),
        "resource_groups": repo.distinct_values("resource_group", base, limit=1000),
        "resource_types": repo.distinct_values("resource_type", base, limit=500),
        "meter_categories": repo.distinct_values("meter_category", base, limit=500),
        "tag_keys": repo.tag_keys(),
        "presets": [{"value": k, "label": v} for k, v in PRESETS.items()],
        "comparison_modes": [{"value": k, "label": v} for k, v in COMPARISON_MODES.items()],
        "group_by": [{"value": k, "label": v} for k, v in GROUP_BY_OPTIONS.items()],
        "week_start_isodow": settings_service.week_start(db),
        "default_currency": settings_service.get_setting(db, "reporting.default_currency"),
        "default_waterfall_top_n": settings_service.get_setting(db, "reporting.default_waterfall_top_n"),
    }


@router.get("/freshness", summary="Data freshness and ingestion health")
def freshness(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return freshness_service.overall_freshness(db, user.allowed_subscription_fks)
