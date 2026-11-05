"""Subscription, application and attribution configuration tables."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Application(TimestampMixin, Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    subscriptions: Mapped[list[AzureSubscription]] = relationship(back_populates="application")


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # production | non_production | shared | unallocated -- used for the global filter
    environment_group: Mapped[str] = mapped_column(String(32), nullable=False)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class AzureSubscription(TimestampMixin, Base):
    __tablename__ = "azure_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    subscription_name: Mapped[str] = mapped_column(String(200), nullable=False)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"))
    tenant_id: Mapped[str | None] = mapped_column(String(64))
    billing_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Connection test state (written by Administration -> Azure Connections)
    connection_status: Mapped[str] = mapped_column(String(32), default="untested", nullable=False)
    auth_status: Mapped[str] = mapped_column(String(32), default="untested", nullable=False)
    cost_api_status: Mapped[str] = mapped_column(String(32), default="untested", nullable=False)
    storage_status: Mapped[str] = mapped_column(String(32), default="untested", nullable=False)
    last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Synchronisation state (written by the ingestion worker)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application | None] = relationship(back_populates="subscriptions")
    environment: Mapped[Environment | None] = relationship()
    export_definitions: Mapped[list[ExportDefinition]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )


class ExportDefinition(TimestampMixin, Base):
    """A Cost Management export whose files the worker ingests.

    Exports are expected to be created by an administrator or IaC (least privilege);
    the platform only reads their output.
    """

    __tablename__ = "export_definitions"
    __table_args__ = (UniqueConstraint("subscription_fk", "dataset_type", "export_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_fk: Mapped[int] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)  # actual | amortized | focus
    export_name: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_account_url: Mapped[str | None] = mapped_column(String(500))  # null -> global setting
    container: Mapped[str] = mapped_column(String(200), nullable=False)
    root_folder_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), default="csv", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_discovery_error: Mapped[str | None] = mapped_column(Text)

    subscription: Mapped[AzureSubscription] = relationship(back_populates="export_definitions")

    @property
    def blob_prefix(self) -> str:
        parts = [p.strip("/") for p in (self.root_folder_path, self.export_name) if p and p.strip("/")]
        return "/".join(parts) + "/"


class ResourceGroup(Base):
    __tablename__ = "resource_groups"
    __table_args__ = (UniqueConstraint("subscription_fk", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_fk: Mapped[int] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # lower-cased
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_seen_date: Mapped[date | None] = mapped_column(Date)
    last_seen_date: Mapped[date | None] = mapped_column(Date)


class AzureResource(Base):
    """Resource inventory derived from billing data (latest known attributes)."""

    __tablename__ = "azure_resources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    resource_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # lower-cased ARM id
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(400))
    resource_type: Mapped[str | None] = mapped_column(String(300))
    subscription_fk: Mapped[int] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"), nullable=False)
    resource_group: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(200))
    service_category: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    application_id: Mapped[int | None] = mapped_column(Integer)
    environment_id: Mapped[int | None] = mapped_column(Integer)
    allocation_status: Mapped[str | None] = mapped_column(String(32))
    owner: Mapped[str | None] = mapped_column(String(200))
    cost_center: Mapped[str | None] = mapped_column(String(200))
    first_seen_date: Mapped[date | None] = mapped_column(Date)
    last_seen_date: Mapped[date | None] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ResourceTagMapping(TimestampMixin, Base):
    """Map a resource tag to an attribution dimension.

    ``tag_value`` null  -> any value of the tag matches.
    ``target_value`` null -> the tag value itself becomes the dimension value.
    """

    __tablename__ = "resource_tag_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_key: Mapped[str] = mapped_column(String(200), nullable=False)
    tag_value: Mapped[str | None] = mapped_column(String(400))
    target_dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    target_value: Mapped[str | None] = mapped_column(String(400))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class ApplicationMapping(TimestampMixin, Base):
    """Resource-group / resource pattern mapping to application, environment and allocation."""

    __tablename__ = "application_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)  # resource_group | resource_id
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)  # case-insensitive glob
    subscription_fk: Mapped[int | None] = mapped_column(ForeignKey("azure_subscriptions.id", ondelete="CASCADE"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"))
    allocation_status: Mapped[str] = mapped_column(String(32), default="allocated", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class ServiceCategoryRule(TimestampMixin, Base):
    """Classify billing rows into reporting service categories (first match by priority)."""

    __tablename__ = "service_category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_field: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
