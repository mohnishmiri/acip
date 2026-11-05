"""Anomalies, budgets, forecasts, savings opportunities and saved comparisons."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, TimestampMixin


class AnomalyRule(TimestampMixin, Base):
    __tablename__ = "anomaly_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # daily_spike | weekly_spike | monthly_spike | new_resource | continuous_increase
    detection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # subscription_service | resource | application_environment | subscription
    scope_level: Mapped[str] = mapped_column(String(64), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CostAnomaly(Base):
    __tablename__ = "cost_anomalies"
    __table_args__ = (
        Index("ix_cost_anomalies_status", "status", "detection_date"),
        Index("ix_cost_anomalies_scope", "rule_code", "scope_key", "last_detected_date"),
        Index("ix_cost_anomalies_resource", "resource_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_rules.id", ondelete="SET NULL"))
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    detection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_level: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    detection_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subscription_fk: Mapped[int | None] = mapped_column(Integer)
    application_id: Mapped[int | None] = mapped_column(Integer)
    environment_id: Mapped[int | None] = mapped_column(Integer)
    service_category: Mapped[str | None] = mapped_column(String(100))
    resource_group: Mapped[str | None] = mapped_column(String(200))
    resource_key: Mapped[str | None] = mapped_column(Text)
    resource_name: Mapped[str | None] = mapped_column(String(400))
    previous_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    current_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    expected_baseline: Mapped[Decimal] = mapped_column(Money, nullable=False)
    absolute_increase: Mapped[Decimal] = mapped_column(Money, nullable=False)
    percentage_increase: Mapped[Decimal | None] = mapped_column(Money)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    # open | investigating | acknowledged | resolved | dismissed | expected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_steps: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    __table_args__ = (Index("ix_anomaly_events_anomaly", "anomaly_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("cost_anomalies.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # detected | redetected | status_change | comment
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CostComparison(Base):
    """Saved comparison definitions (re-run on demand against current data)."""

    __tablename__ = "cost_comparisons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastRecord(Base):
    __tablename__ = "forecast_records"
    __table_args__ = (Index("ix_forecast_records_scope", "scope_type", "scope_ref", "generated_on"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    generated_on: Mapped[date] = mapped_column(Date, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String(200))
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    actual_to_date: Mapped[Decimal] = mapped_column(Money, nullable=False)
    forecast_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # total | application | subscription | environment | resource_group
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String(300))
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)  # monthly | annual
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(32), nullable=False, default="actual")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    thresholds: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=lambda: [70, 80, 90, 100])
    forecast_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False, default="system")


class SavingsOpportunity(Base):
    __tablename__ = "savings_opportunities"
    __table_args__ = (Index("ix_savings_status", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opportunity_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    resource_key: Mapped[str | None] = mapped_column(Text)
    resource_name: Mapped[str | None] = mapped_column(String(400))
    subscription_fk: Mapped[int | None] = mapped_column(Integer)
    application_id: Mapped[int | None] = mapped_column(Integer)
    environment_id: Mapped[int | None] = mapped_column(Integer)
    service_category: Mapped[str | None] = mapped_column(String(100))
    billing_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_monthly_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    estimated_monthly_savings: Mapped[Decimal | None] = mapped_column(Money)
    savings_basis: Mapped[str | None] = mapped_column(Text)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(64), nullable=False)  # billing_analysis | azure_advisor
    # open | investigating | accepted | dismissed | implemented
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
