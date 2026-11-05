"""Subscription registration (admin UI and AZURE_SUBSCRIPTIONS_CONFIG)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models import Application, AzureSubscription, Environment, ExportDefinition

log = logging.getLogger(__name__)
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _env_id(db: Session, code: str | None) -> int | None:
    if not code:
        return None
    env = db.execute(select(Environment).where(Environment.code == code)).scalar_one_or_none()
    if env is None:
        raise ValidationFailed(f"Unknown environment '{code}'")
    return env.id


def default_exports(subscription_id: str) -> list[dict[str, Any]]:
    s = get_settings()
    return [
        {"dataset_type": "actual", "export_name": "acip-actual-daily", "container": s.azure_cost_export_container, "root_folder_path": f"subscriptions/{subscription_id}/actual"},
        {"dataset_type": "amortized", "export_name": "acip-amortized-daily", "container": s.azure_cost_export_container, "root_folder_path": f"subscriptions/{subscription_id}/amortized"},
    ]


def upsert_subscription(db: Session, data: dict[str, Any]) -> AzureSubscription:
    sid = str(data.get("subscription_id", "")).strip().lower()
    if not GUID_RE.match(sid):
        raise ValidationFailed("subscription_id must be a GUID")
    if data.get("tenant_id") and not GUID_RE.match(str(data["tenant_id"])):
        raise ValidationFailed("tenant_id must be a GUID")
    currency = str(data.get("billing_currency") or "USD").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValidationFailed("billing_currency must be an ISO-4217 code")
    app_id = data.get("application_id")
    if app_id is None and data.get("application"):
        app = db.execute(select(Application).where(Application.code == data["application"])).scalar_one_or_none()
        if app is None:
            raise ValidationFailed(f"Unknown application '{data['application']}'")
        app_id = app.id
    if app_id is not None and db.get(Application, app_id) is None:
        raise ValidationFailed(f"Unknown application id {app_id}")
    env_id = data.get("environment_id") or _env_id(db, data.get("environment"))

    sub = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == sid)).scalar_one_or_none()
    if sub is None:
        sub = AzureSubscription(subscription_id=sid, subscription_name=data.get("subscription_name") or sid)
        db.add(sub)
    sub.subscription_name = data.get("subscription_name") or sub.subscription_name
    sub.application_id = app_id
    sub.environment_id = env_id
    sub.tenant_id = data.get("tenant_id") or get_settings().azure_tenant_id
    sub.billing_currency = currency
    sub.enabled = bool(data.get("enabled", True))
    sub.is_demo = bool(data.get("is_demo", sub.is_demo or False))
    db.flush()
    exports = data.get("exports")
    if exports is None and not sub.export_definitions:
        exports = default_exports(sid)
    if exports is not None:
        set_exports(db, sub, exports)
    return sub


def set_exports(db: Session, sub: AzureSubscription, exports: list[dict[str, Any]]) -> None:
    keep = set()
    for e in exports:
        ds = e.get("dataset_type")
        if ds not in ("actual", "amortized", "focus"):
            raise ValidationFailed("dataset_type must be actual, amortized or focus")
        name = e.get("export_name") or f"acip-{ds}-daily"
        ed = next((x for x in sub.export_definitions if x.dataset_type == ds and x.export_name == name), None)
        if ed is None:
            ed = ExportDefinition(subscription_fk=sub.id, dataset_type=ds, export_name=name, container=e.get("container") or get_settings().azure_cost_export_container)
            sub.export_definitions.append(ed)
        ed.container = e.get("container") or ed.container
        ed.root_folder_path = e.get("root_folder_path", ed.root_folder_path or "")
        ed.storage_account_url = e.get("storage_account_url") or ed.storage_account_url
        ed.enabled = bool(e.get("enabled", True))
        keep.add((ds, name))
    for ed in list(sub.export_definitions):
        if (ed.dataset_type, ed.export_name) not in keep:
            sub.export_definitions.remove(ed)
    db.flush()


def load_config_file(db: Session) -> dict[str, int]:
    """Register applications and subscriptions from AZURE_SUBSCRIPTIONS_CONFIG (path or JSON)."""
    raw = get_settings().azure_subscriptions_config
    if not raw:
        return {"applications": 0, "subscriptions": 0}
    text = raw
    if not raw.strip().startswith("{"):
        if not os.path.exists(raw):
            log.warning("AZURE_SUBSCRIPTIONS_CONFIG points to a file that does not exist; skipping", extra={"path": raw})
            return {"applications": 0, "subscriptions": 0, "skipped": 1}
        with open(raw, encoding="utf-8") as fh:
            text = fh.read()
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"AZURE_SUBSCRIPTIONS_CONFIG is not valid JSON: {exc}") from exc
    apps = 0
    for a in cfg.get("applications", []):
        app = db.execute(select(Application).where(Application.code == a["code"])).scalar_one_or_none()
        if app is None:
            app = Application(code=a["code"], name=a.get("name", a["code"]))
            db.add(app)
            apps += 1
        app.name = a.get("name", app.name)
        app.description = a.get("description", app.description)
        app.owner = a.get("owner", app.owner)
        app.sort_order = a.get("sort_order", app.sort_order or 100)
    db.flush()
    subs = 0
    for s in cfg.get("subscriptions", []):
        upsert_subscription(db, s)
        subs += 1
    return {"applications": apps, "subscriptions": subs}


def get_subscription(db: Session, subscription_id: str) -> AzureSubscription:
    sub = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == subscription_id.lower())).scalar_one_or_none()
    if sub is None:
        raise NotFoundError(f"Subscription {subscription_id} is not registered")
    return sub


def delete_subscription(db: Session, subscription_id: str) -> None:
    sub = get_subscription(db, subscription_id)
    from sqlalchemy import func

    from app.models import DailyCostAggregate

    has_data = db.execute(select(func.count()).select_from(DailyCostAggregate).where(DailyCostAggregate.subscription_fk == sub.id)).scalar_one()
    if has_data:
        raise ConflictError("Subscription has ingested cost data; disable it instead of deleting to preserve history and audit trail.")
    db.delete(sub)


def serialize(sub: AzureSubscription) -> dict[str, Any]:
    return {
        "id": sub.id,
        "subscription_id": sub.subscription_id,
        "subscription_name": sub.subscription_name,
        "application_id": sub.application_id,
        "application_name": sub.application.name if sub.application else None,
        "environment": sub.environment.code if sub.environment else None,
        "environment_name": sub.environment.name if sub.environment else None,
        "tenant_id": sub.tenant_id,
        "billing_currency": sub.billing_currency,
        "enabled": sub.enabled,
        "is_demo": sub.is_demo,
        "connection_status": sub.connection_status,
        "auth_status": sub.auth_status,
        "cost_api_status": sub.cost_api_status,
        "storage_status": sub.storage_status,
        "last_connection_test_at": sub.last_connection_test_at.isoformat() if sub.last_connection_test_at else None,
        "connection_details": sub.connection_details,
        "last_successful_sync_at": sub.last_successful_sync_at.isoformat() if sub.last_successful_sync_at else None,
        "last_sync_attempt_at": sub.last_sync_attempt_at.isoformat() if sub.last_sync_attempt_at else None,
        "last_sync_error": sub.last_sync_error,
        "exports": [
            {
                "id": e.id,
                "dataset_type": e.dataset_type,
                "export_name": e.export_name,
                "container": e.container,
                "root_folder_path": e.root_folder_path,
                "storage_account_url": e.storage_account_url,
                "enabled": e.enabled,
                "blob_prefix": e.blob_prefix,
                "last_discovery_at": e.last_discovery_at.isoformat() if e.last_discovery_at else None,
                "last_discovery_error": e.last_discovery_error,
            }
            for e in sub.export_definitions
        ],
    }
