from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import AzureSubscription
from app.schemas.common import ConnectionTestRequest
from app.security.auth import CurrentUser, require
from app.services import audit_service, connection_service
from app.services.subscription_service import serialize

router = APIRouter(prefix="/azure", tags=["Azure Connections"])


@router.get("/connections", summary="Connection status for every registered subscription")
def connections(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    s = get_settings()
    subs = [serialize(x) for x in db.execute(select(AzureSubscription).order_by(AzureSubscription.id)).scalars()
            if user.allowed_subscription_fks is None or x.id in user.allowed_subscription_fks]
    return {
        "identity": {
            "auth_mode": s.azure_auth_mode,
            "tenant_id": s.azure_tenant_id,
            "client_id": s.azure_client_id,
            "client_secret_configured": bool(s.azure_client_secret),
            "storage_account_url": s.azure_storage_account_url,
            "export_source": s.effective_export_source,
            "note": "One existing service principal is used for all subscriptions. Secrets and tokens are never returned to the browser.",
        },
        "subscriptions": subs,
    }


@router.post("/connections/test", summary="Test all (or selected) subscriptions independently")
def test_connections(body: ConnectionTestRequest, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    results = connection_service.test_all(db, body.subscription_ids)
    audit_service.record(db, user, "azure.connections.test", details={"subscriptions": [r["subscription_id"] for r in results]}, request=request)
    db.commit()
    return {"results": results}


@router.post("/connections/{subscription_id}/test", summary="Test one subscription")
def test_one(subscription_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    results = connection_service.test_all(db, [subscription_id])
    audit_service.record(db, user, "azure.connections.test", entity_type="subscription", entity_id=subscription_id, request=request)
    db.commit()
    return {"results": results}


@router.get("/subscriptions/discover", summary="Subscriptions visible to the collection service principal")
def discover(db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    return connection_service.discover_subscriptions(db)
