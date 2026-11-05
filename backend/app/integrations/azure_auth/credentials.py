"""Credential factory for the existing collection Service Principal.

One identity (the existing Entra application registration / service principal) is used
for every subscription:

* ``client_secret``     -- local Docker development (AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET).
* ``workload_identity`` -- AKS. The same app registration is federated with the Kubernetes
                           service account; the webhook injects AZURE_FEDERATED_TOKEN_FILE so
                           no long-lived secret is stored in the cluster.
* ``managed_identity`` / ``default`` -- supported for completeness.

azure-identity caches tokens and renews them before expiry; tokens never leave the backend.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError

log = logging.getLogger(__name__)

ARM_SCOPE = "https://management.azure.com/.default"
STORAGE_SCOPE = "https://storage.azure.com/.default"

_lock = threading.Lock()
_credential: Any = None


class AzureNotConfigured(AppError):
    status_code = 409
    code = "azure_not_configured"


def build_credential(settings: Settings | None = None):
    settings = settings or get_settings()
    mode = settings.azure_auth_mode
    if mode == "disabled":
        raise AzureNotConfigured("Azure integration is disabled (AZURE_AUTH_MODE=disabled). The platform is running on demo/local data.")
    from azure.identity import (
        ClientSecretCredential,
        DefaultAzureCredential,
        ManagedIdentityCredential,
        WorkloadIdentityCredential,
    )

    if mode == "client_secret":
        missing = [n for n, v in (("AZURE_TENANT_ID", settings.azure_tenant_id), ("AZURE_CLIENT_ID", settings.azure_client_id), ("AZURE_CLIENT_SECRET", settings.azure_client_secret)) if not v]
        if missing:
            raise AzureNotConfigured(f"Missing configuration for client_secret auth: {', '.join(missing)}")
        return ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret.get_secret_value(),  # type: ignore[union-attr]
        )
    if mode == "workload_identity":
        # tenant/client id/token file default to the AZURE_* variables injected by the webhook
        kwargs: dict[str, Any] = {}
        if settings.azure_tenant_id:
            kwargs["tenant_id"] = settings.azure_tenant_id
        if settings.azure_client_id:
            kwargs["client_id"] = settings.azure_client_id
        return WorkloadIdentityCredential(**kwargs)
    if mode == "managed_identity":
        return ManagedIdentityCredential(client_id=settings.azure_client_id) if settings.azure_client_id else ManagedIdentityCredential()
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def get_credential():
    """Process-wide credential (token cache shared across requests and jobs)."""
    global _credential
    with _lock:
        if _credential is None:
            _credential = build_credential()
        return _credential


def reset_credential() -> None:
    global _credential
    with _lock:
        _credential = None


def acquire_arm_token() -> tuple[str, int]:
    """Return (access_token, expires_on). Raises on failure with the Entra error text."""
    tok = get_credential().get_token(ARM_SCOPE)
    return tok.token, tok.expires_on
