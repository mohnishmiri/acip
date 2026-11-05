from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security.auth import CurrentUser


def record(db: Session, user: CurrentUser, action: str, *, entity_type: str | None = None, entity_id: str | None = None,
           details: dict[str, Any] | None = None, request: Request | None = None) -> None:
    db.add(AuditLog(
        actor=user.email or user.name,
        actor_id=user.external_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip_address=request.client.host if request and request.client else None,
    ))
