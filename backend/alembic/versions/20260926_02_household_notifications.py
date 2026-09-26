"""Persistent household application notifications.

Revision ID: 20260926_02
Revises: 20260926_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260926_02"
down_revision = "20260926_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["shared"]

def upgrade() -> None:
    op.create_table(
        "household_notifications",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("recipient_user_id", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="info"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("target_route", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("household_id", "recipient_user_id", "source_type", "source_key", name="uq_household_notification_source"),
    )
    op.create_index("idx_household_notifications_inbox", "household_notifications", ["household_id", "recipient_user_id", "created_at"])

def downgrade() -> None:
    op.drop_index("idx_household_notifications_inbox", table_name="household_notifications")
    op.drop_table("household_notifications")
