"""email notifications: alert rule recipients and notification deliveries

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_rules", sa.Column("email_recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"))
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_message_id", sa.String(length=300), nullable=True),
        sa.Column("subject", sa.String(length=400), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notification_history.id"], name=op.f("fk_notification_deliveries_notification_id_notification_history"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint("notification_id", "channel", name=op.f("uq_notification_deliveries_notification_id_channel")),
    )
    op.create_index("ix_notification_deliveries_queue", "notification_deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_queue", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_column("alert_rules", "email_recipients")
