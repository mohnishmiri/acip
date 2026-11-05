"""Application user authentication (Microsoft Entra ID) and role-based access control.

This identity is completely separate from the cost-collection service principal:
users sign in to the SPA with their own Entra account; the SPA calls this API with an
access token for the ACIP API app registration; the API validates the token here.

Roles come from Entra *app roles* in the token (``roles`` claim) and/or database role
assignments. A database assignment may be scoped to one application, which restricts
the user to that application's subscriptions (subscription-level authorisation).

``APP_AUTH_MODE=disabled`` is for local development only: every request runs as a local
administrator (optionally downgraded with the ``X-ACIP-Dev-Role`` header for testing).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AuthenticationError, PermissionDenied
from app.models import AzureSubscription, Role, User, UserRoleAssignment

log = logging.getLogger(__name__)

PERMISSIONS: dict[str, set[str]] = {
    "administrator": {"read", "export", "manage_budgets", "manage_anomalies", "manage_savings", "manage_alerts", "admin", "ingestion"},
    "finops_analyst": {"read", "export", "manage_budgets", "manage_anomalies", "manage_savings", "manage_alerts"},
    "engineering_lead": {"read", "export", "manage_anomalies", "manage_savings"},
    "viewer": {"read", "export"},
}
ROLE_ORDER = ["administrator", "finops_analyst", "engineering_lead", "viewer"]


@dataclass
class CurrentUser:
    external_id: str
    name: str
    email: str | None
    roles: set[str]
    auth_mode: str
    id: int | None = None
    allowed_subscription_fks: set[int] | None = None  # None = all subscriptions
    scoped_application_ids: set[int] | None = None
    permissions: set[str] = field(default_factory=set)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def primary_role(self) -> str | None:
        return next((r for r in ROLE_ORDER if r in self.roles), None)


_jwk_lock = threading.Lock()
_jwk_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    global _jwk_client
    s = get_settings()
    with _jwk_lock:
        if _jwk_client is None:
            _jwk_client = jwt.PyJWKClient(f"{s.entra_authority_host}/{s.entra_tenant_id}/discovery/v2.0/keys", cache_keys=True, lifespan=3600)
        return _jwk_client


def validate_token(token: str) -> dict:
    s = get_settings()
    if not (s.entra_tenant_id and s.api_audience):
        raise AuthenticationError("Entra authentication is not configured (ENTRA_TENANT_ID / ENTRA_API_CLIENT_ID)")
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        audiences = [a for a in {s.api_audience, s.entra_api_client_id} if a]
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=f"{s.entra_authority_host}/{s.entra_tenant_id}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Invalid access token: {exc}") from exc
    if claims.get("tid") and claims["tid"] != s.entra_tenant_id:
        raise AuthenticationError("Token issued for a different tenant")
    return claims


def _finalise(db: Session, user: CurrentUser) -> CurrentUser:
    user.permissions = set().union(*(PERMISSIONS.get(r, set()) for r in user.roles)) if user.roles else set()
    if user.scoped_application_ids is not None:
        user.allowed_subscription_fks = {
            s.id for s in db.execute(select(AzureSubscription).where(AzureSubscription.application_id.in_(user.scoped_application_ids))).scalars()
        }
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    s = get_settings()
    if s.app_auth_mode == "disabled":
        role = request.headers.get("X-ACIP-Dev-Role", "administrator")
        if role not in PERMISSIONS:
            role = "viewer"
        user = CurrentUser(external_id="local-dev", name="Local Developer", email=None, roles={role}, auth_mode="disabled")
        scope = request.headers.get("X-ACIP-Dev-Application")
        if scope and scope.isdigit():
            user.scoped_application_ids = {int(scope)}
        return _finalise(db, user)

    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token")
    claims = validate_token(header.split(" ", 1)[1].strip())
    oid = claims.get("oid") or claims.get("sub")
    name = claims.get("name") or claims.get("preferred_username") or oid
    email = claims.get("preferred_username") or claims.get("upn") or claims.get("email")

    db_user = db.execute(select(User).where(User.external_id == oid)).scalar_one_or_none()
    if db_user is None:
        db_user = User(external_id=oid, email=email, display_name=name)
        db.add(db_user)
    db_user.last_login_at = datetime.now(UTC)
    db_user.email = email or db_user.email
    db_user.display_name = name or db_user.display_name
    db.flush()

    role_by_app_role = {r.entra_app_role: r.code for r in db.execute(select(Role)).scalars() if r.entra_app_role}
    token_roles = {role_by_app_role[r] for r in claims.get("roles", []) if r in role_by_app_role}
    global_roles = set(token_roles)
    scoped_apps: set[int] = set()
    scoped_roles: set[str] = set()
    for a, r in db.execute(select(UserRoleAssignment, Role).join(Role, Role.id == UserRoleAssignment.role_id).where(UserRoleAssignment.user_id == db_user.id)):
        if a.application_id is None:
            global_roles.add(r.code)
        else:
            scoped_apps.add(a.application_id)
            scoped_roles.add(r.code)
    db.commit()
    if not global_roles and not scoped_roles:
        raise PermissionDenied("Your account has no ACIP role. Ask an administrator to assign an app role (ACIP.Viewer or higher).")
    user = CurrentUser(external_id=oid, name=name, email=email, roles=global_roles | scoped_roles, auth_mode="entra", id=db_user.id)
    if not global_roles:
        user.scoped_application_ids = scoped_apps
    return _finalise(db, user)


def require(permission: str):
    def dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.can(permission):
            raise PermissionDenied(f"This action requires the '{permission}' permission (your role: {user.primary_role or 'none'}).")
        return user

    return dep
