"""Cost fact and aggregate tables.

``cost_records`` holds normalised export rows and is range-partitioned by month on
``usage_date`` (see the initial migration). Reporting queries never scan it for
dashboards; they read the pre-aggregated tables below, which are rebuilt per
(subscription, dataset, date range) slice whenever an export run is applied.

Column names are deliberately identical across raw and aggregate tables so a single
query builder can target whichever table satisfies the requested dimensions.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, Qty

cost_records_id_seq = Sequence("cost_records_id_seq")


class _CostDims:
    """Dimension columns shared by raw records and aggregates."""

    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subscription_fk: Mapped[int] = mapped_column(Integer, nullable=False)
    application_id: Mapped[int | None] = mapped_column(Integer)
    environment_id: Mapped[int | None] = mapped_column(Integer)
    allocation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unallocated")
    service_category: Mapped[str] = mapped_column(String(100), nullable=False, default="Other Services")
    region: Mapped[str | None] = mapped_column(String(100))
    charge_type: Mapped[str | None] = mapped_column(String(64))
    pricing_model: Mapped[str | None] = mapped_column(String(64))
    owner: Mapped[str | None] = mapped_column(String(200))
    cost_center: Mapped[str | None] = mapped_column(String(200))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CostRecord(_CostDims, Base):
    __tablename__ = "cost_records"
    __table_args__ = (
        PrimaryKeyConstraint("id", "usage_date"),
        {"postgresql_partition_by": "RANGE (usage_date)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, cost_records_id_seq, server_default=cost_records_id_seq.next_value())
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    export_run_id: Mapped[int | None] = mapped_column(BigInteger)
    ingestion_file_id: Mapped[int | None] = mapped_column(BigInteger)
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    billing_period_start: Mapped[date | None] = mapped_column(Date)
    billing_period_end: Mapped[date | None] = mapped_column(Date)

    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Money)
    payg_cost: Mapped[Decimal | None] = mapped_column(Money)
    quantity: Mapped[Decimal | None] = mapped_column(Qty)
    unit_of_measure: Mapped[str | None] = mapped_column(String(100))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    effective_price: Mapped[Decimal | None] = mapped_column(Money)

    resource_id: Mapped[str | None] = mapped_column(Text)
    resource_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resource_name: Mapped[str | None] = mapped_column(String(400))
    resource_group: Mapped[str | None] = mapped_column(String(200))
    resource_type: Mapped[str | None] = mapped_column(String(300))

    service_name: Mapped[str | None] = mapped_column(String(200))
    service_family: Mapped[str | None] = mapped_column(String(200))
    consumed_service: Mapped[str | None] = mapped_column(String(200))
    meter_id: Mapped[str | None] = mapped_column(String(100))
    meter_name: Mapped[str | None] = mapped_column(String(300))
    meter_category: Mapped[str | None] = mapped_column(String(200))
    meter_subcategory: Mapped[str | None] = mapped_column(String(300))
    meter_region: Mapped[str | None] = mapped_column(String(100))
    product_name: Mapped[str | None] = mapped_column(String(400))
    sku: Mapped[str | None] = mapped_column(String(200))
    frequency: Mapped[str | None] = mapped_column(String(64))
    benefit_id: Mapped[str | None] = mapped_column(String(300))
    benefit_name: Mapped[str | None] = mapped_column(String(300))
    publisher_type: Mapped[str | None] = mapped_column(String(64))
    source_cost_center: Mapped[str | None] = mapped_column(String(200))  # export 'CostCenter' column (EA)

    tags: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    additional_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    project: Mapped[str | None] = mapped_column(String(200))
    team: Mapped[str | None] = mapped_column(String(200))
    business_unit: Mapped[str | None] = mapped_column(String(200))
    workload: Mapped[str | None] = mapped_column(String(200))
    attribution_source: Mapped[str | None] = mapped_column(String(200))
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CostDataSlice(Base):
    """Which export run supplied each (subscription, dataset, day).

    Guarantees replace-not-append semantics: a day is only overwritten by a run whose
    submission time is the same or newer than the run that last supplied it.
    """

    __tablename__ = "cost_data_slices"
    __table_args__ = (PrimaryKeyConstraint("subscription_fk", "dataset_type", "usage_date"),)

    subscription_fk: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    export_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DailyCostAggregate(_CostDims, Base):
    """Coarse daily grain (no resource / meter). Backs most dashboard queries."""

    __tablename__ = "daily_cost_aggregates"
    __table_args__ = (
        Index("ix_dca_main", "dataset_type", "billing_currency", "usage_date"),
        Index("ix_dca_sub_date", "subscription_fk", "dataset_type", "usage_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)


class MonthlyCostAggregate(_CostDims, Base):
    __tablename__ = "monthly_cost_aggregates"
    __table_args__ = (
        Index("ix_mca_main", "dataset_type", "billing_currency", "usage_date"),
        Index("ix_mca_sub_date", "subscription_fk", "dataset_type", "usage_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)  # first day of month
    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ResourceCostAggregate(_CostDims, Base):
    """Daily grain per resource (no meter)."""

    __tablename__ = "resource_cost_aggregates"
    __table_args__ = (
        Index("ix_rca_main", "dataset_type", "billing_currency", "usage_date"),
        Index("ix_rca_resource", "resource_key", "dataset_type", "usage_date"),
        Index("ix_rca_sub_date", "subscription_fk", "dataset_type", "usage_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    resource_key: Mapped[str] = mapped_column(Text, nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(400))
    resource_group: Mapped[str | None] = mapped_column(String(200))
    resource_type: Mapped[str | None] = mapped_column(String(300))
    tags: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)


class MeterCostAggregate(_CostDims, Base):
    """Daily grain per resource x meter (finest pre-aggregated level)."""

    __tablename__ = "meter_cost_aggregates"
    __table_args__ = (
        Index("ix_mtca_main", "dataset_type", "billing_currency", "usage_date"),
        Index("ix_mtca_resource", "resource_key", "dataset_type", "usage_date"),
        Index("ix_mtca_sub_date", "subscription_fk", "dataset_type", "usage_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    resource_key: Mapped[str] = mapped_column(Text, nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(400))
    resource_group: Mapped[str | None] = mapped_column(String(200))
    resource_type: Mapped[str | None] = mapped_column(String(300))
    meter_id: Mapped[str | None] = mapped_column(String(100))
    meter_category: Mapped[str | None] = mapped_column(String(200))
    meter_subcategory: Mapped[str | None] = mapped_column(String(300))
    meter_name: Mapped[str | None] = mapped_column(String(300))
    unit_of_measure: Mapped[str | None] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(200))
    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Qty)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
