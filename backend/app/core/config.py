"""Application configuration.

All runtime configuration comes from environment variables (12-factor). Business rules
that administrators may change at runtime (week start, anomaly thresholds, ...) live in
the ``application_settings`` table instead -- see ``app.services.settings_service``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # --- General -------------------------------------------------------------------
    app_name: str = "Azure Cost Intelligence Platform"
    app_env: str = Field(default="local", description="local | development | staging | production")
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    cors_origins: str = "http://localhost:3000"

    # --- Database ------------------------------------------------------------------
    database_url: str = "postgresql+psycopg://acip:acip@postgres:5432/acip"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_statement_timeout_ms: int = 60000  # interactive API requests
    db_batch_statement_timeout_ms: int = 900000  # worker / CLI batch work (ingestion, aggregation)

    # --- Demo mode -----------------------------------------------------------------
    demo_mode: bool = Field(default=True, description="Seed and display clearly-labelled DEMO data")

    # --- Application user authentication (separate from the collection identity) ---
    app_auth_mode: Literal["disabled", "entra"] = "disabled"
    entra_tenant_id: str | None = None
    entra_api_client_id: str | None = Field(default=None, description="App registration exposing the ACIP API")
    entra_api_audience: str | None = Field(default=None, description="Expected 'aud' claim; defaults to api://<client id>")
    entra_spa_client_id: str | None = Field(default=None, description="SPA app registration used by the browser")
    entra_api_scope: str | None = Field(default=None, description="Scope requested by the SPA, e.g. api://<id>/access_as_user")
    entra_authority_host: str = "https://login.microsoftonline.com"

    # --- Azure cost collection identity (existing Service Principal) ----------------
    azure_auth_mode: Literal["disabled", "client_secret", "workload_identity", "managed_identity", "default"] = "disabled"
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: SecretStr | None = None
    azure_subscriptions_config: str | None = Field(
        default=None, description="Path to a JSON file, or inline JSON, describing subscriptions to register"
    )
    azure_storage_account_url: str | None = None
    azure_cost_export_container: str = "cost-exports"
    azure_arm_endpoint: str = "https://management.azure.com"
    azure_http_timeout_seconds: int = 30

    # --- Export source -------------------------------------------------------------
    export_source: Literal["auto", "azure_blob", "local"] = "auto"
    local_export_root: str = "/data/exports"

    # --- Worker --------------------------------------------------------------------
    worker_poll_interval_seconds: int = 5
    export_discovery_interval_minutes: int = 60
    analytics_interval_minutes: int = 360
    job_max_attempts: int = 3
    job_retry_backoff_seconds: int = 60
    job_stale_after_minutes: int = 60
    ingestion_reject_threshold_pct: float = 1.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def azure_enabled(self) -> bool:
        return self.azure_auth_mode != "disabled"

    @property
    def effective_export_source(self) -> str:
        if self.export_source != "auto":
            return self.export_source
        if self.azure_enabled and self.azure_storage_account_url:
            return "azure_blob"
        return "local"

    @property
    def api_audience(self) -> str | None:
        if self.entra_api_audience:
            return self.entra_api_audience
        if self.entra_api_client_id:
            return f"api://{self.entra_api_client_id}"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
