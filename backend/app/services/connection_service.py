"""Per-subscription Azure connection validation.

Each subscription is tested independently; a failure in one never stops the others.
Access is validated by calling the real APIs rather than assuming that a successful
token acquisition implies permission.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AzureSubscription

log = logging.getLogger(__name__)

REMEDIATION = {
    "auth": "Check AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET (local) or the Workload Identity federation (AKS) for the existing collection service principal.",
    "subscription": "Grant the collection service principal at least 'Reader' or 'Cost Management Reader' on /subscriptions/{sid}.",
    "cost": "Assign the 'Cost Management Reader' role on /subscriptions/{sid} to the existing collection service principal. Owner or Contributor is NOT required.",
    "storage": "Assign 'Storage Blob Data Reader' on the export storage account (or container) to the collection service principal, and check that the export container and folder exist.",
}


def _step(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **extra}


def test_subscription(db: Session, sub: AzureSubscription) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    result: dict[str, Any] = {"subscription_id": sub.subscription_id, "tested_at": now.isoformat(), "steps": {}}
    steps = result["steps"]

    if sub.is_demo:
        for k in ("auth", "subscription", "cost_api", "exports", "storage"):
            steps[k] = _step("demo", "Demo subscription — no Azure connection is made; data comes from generated DEMO export files.")
        from app.integrations.azure_storage.sources import get_export_source

        for e in sub.export_definitions:
            ok, msg = get_export_source(e.storage_account_url).check_access(e.container, e.blob_prefix)
            steps["storage"] = _step("ok" if ok else "failed", f"Local demo exports: {msg}")
        _persist(sub, result, auth="demo", cost="demo", storage=steps["storage"]["status"], overall="demo")
        return result

    if not settings.azure_enabled:
        msg = "Azure integration is disabled (AZURE_AUTH_MODE=disabled)."
        for k in ("auth", "subscription", "cost_api", "exports", "storage"):
            steps[k] = _step("not_configured", msg)
        _persist(sub, result, auth="not_configured", cost="not_configured", storage="not_configured", overall="not_configured")
        return result

    from app.integrations.azure_auth.credentials import acquire_arm_token
    from app.integrations.azure_cost_management.client import ArmClient, ArmError
    from app.integrations.azure_storage.sources import get_export_source

    auth_ok = False
    try:
        _, exp = acquire_arm_token()
        auth_ok = True
        steps["auth"] = _step("ok", f"Token acquired for Azure Resource Manager (mode={settings.azure_auth_mode}); expires {datetime.fromtimestamp(exp, tz=UTC).isoformat()}.")
    except Exception as exc:  # noqa: BLE001
        steps["auth"] = _step("failed", f"Authentication failed: {str(exc)[:600]}", remediation=REMEDIATION["auth"])

    cost_status = "skipped"
    if auth_ok:
        client = ArmClient()
        try:
            info = client.get_subscription(sub.subscription_id)
            steps["subscription"] = _step("ok", f"Subscription visible: {info.get('displayName')} (state {info.get('state')}).", display_name=info.get("displayName"))
        except ArmError as exc:
            steps["subscription"] = _step("failed", f"{exc.status} {exc.code}: {exc.message}", remediation=REMEDIATION["subscription"].format(sid=sub.subscription_id))
        try:
            client.cost_query_probe(sub.subscription_id, (now - timedelta(days=2)).date())
            steps["cost_api"] = _step("ok", "Cost Management query succeeded (read access confirmed).")
            cost_status = "ok"
        except ArmError as exc:
            cost_status = "failed"
            steps["cost_api"] = _step("failed", f"{exc.status} {exc.code}: {exc.message}", remediation=REMEDIATION["cost"].format(sid=sub.subscription_id))
        try:
            exports = client.list_exports(sub.subscription_id)
            names = [e.get("name") for e in exports]
            configured = {e.export_name for e in sub.export_definitions}
            missing = sorted(configured - set(names))
            steps["exports"] = _step("ok" if not missing else "warning",
                                     f"{len(names)} export(s) found in Cost Management" + (f"; not found: {', '.join(missing)}" if missing else ""), exports=names)
        except ArmError as exc:
            steps["exports"] = _step("warning", f"Could not list exports: {exc.status} {exc.code}: {exc.message}")
    else:
        for k in ("subscription", "cost_api", "exports"):
            steps[k] = _step("skipped", "Skipped because authentication failed.")

    storage_status = "ok"
    storage_msgs = []
    for e in sub.export_definitions:
        if not e.enabled:
            continue
        try:
            ok, msg = get_export_source(e.storage_account_url).check_access(e.container, e.blob_prefix)
            storage_msgs.append(f"{e.dataset_type}: {msg}")
            if not ok:
                storage_status = "failed"
        except Exception as exc:  # noqa: BLE001
            storage_status = "failed"
            storage_msgs.append(f"{e.dataset_type}: {str(exc)[:400]}")
    if not sub.export_definitions:
        storage_status = "warning"
        storage_msgs.append("No export definitions configured.")
    steps["storage"] = _step(storage_status, " | ".join(storage_msgs), remediation=REMEDIATION["storage"] if storage_status == "failed" else None)

    if not auth_ok or cost_status == "failed" or steps.get("subscription", {}).get("status") == "failed":
        overall = "failed"
    elif storage_status != "ok" or steps.get("exports", {}).get("status") == "warning":
        overall = "degraded"
    else:
        overall = "ok"
    _persist(sub, result, auth="ok" if auth_ok else "failed", cost=cost_status, storage=storage_status, overall=overall)
    return result


def _persist(sub: AzureSubscription, result: dict[str, Any], *, auth: str, cost: str, storage: str, overall: str) -> None:
    sub.auth_status = auth
    sub.cost_api_status = cost
    sub.storage_status = storage
    sub.connection_status = overall
    sub.last_connection_test_at = datetime.now(UTC)
    sub.connection_details = result
    result["overall"] = overall


def test_all(db: Session, subscription_ids: list[str] | None = None) -> list[dict[str, Any]]:
    q = select(AzureSubscription).order_by(AzureSubscription.id)
    subs = list(db.execute(q).scalars())
    if subscription_ids:
        wanted = {s.lower() for s in subscription_ids}
        subs = [s for s in subs if s.subscription_id in wanted]
    out = []
    for sub in subs:
        try:
            out.append(test_subscription(db, sub))
        except Exception as exc:  # noqa: BLE001 -- isolation per subscription
            log.exception("Connection test crashed", extra={"subscription_id": sub.subscription_id})
            result = {"subscription_id": sub.subscription_id, "steps": {}, "error": str(exc)}
            _persist(sub, result, auth=sub.auth_status, cost=sub.cost_api_status, storage=sub.storage_status, overall="failed")
            out.append(result)
        db.flush()
    return out


def discover_subscriptions(db: Session) -> dict[str, Any]:
    settings = get_settings()
    if not settings.azure_enabled:
        return {"available": False, "reason": "Azure integration is disabled.", "subscriptions": []}
    from app.integrations.azure_cost_management.client import ArmClient

    visible = ArmClient().list_subscriptions()
    registered = {s.subscription_id for s in db.execute(select(AzureSubscription)).scalars()}
    return {
        "available": True,
        "subscriptions": [
            {"subscription_id": v.get("subscriptionId"), "display_name": v.get("displayName"), "state": v.get("state"),
             "tenant_id": v.get("tenantId"), "registered": (v.get("subscriptionId") or "").lower() in registered}
            for v in visible
        ],
    }
