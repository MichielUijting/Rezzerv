"""Add secure account password reset token authority.

Revision ID: 20260902_01
Revises: 20260830_02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260902_01"
down_revision = "20260830_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_password_reset_tokens",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("request_email_hash", sa.String(length=64), nullable=False),
        sa.Column("request_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_users.id"],
            name="fk_account_password_reset_tokens_user_id_app_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_account_password_reset_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_account_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_account_password_reset_tokens_email_requested",
        "account_password_reset_tokens",
        ["request_email_hash", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_account_password_reset_tokens_ip_requested",
        "account_password_reset_tokens",
        ["request_ip_hash", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_account_password_reset_tokens_user_state",
        "account_password_reset_tokens",
        ["user_id", "used_at", "invalidated_at", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_password_reset_tokens_user_state",
        table_name="account_password_reset_tokens",
    )
    op.drop_index(
        "ix_account_password_reset_tokens_ip_requested",
        table_name="account_password_reset_tokens",
    )
    op.drop_index(
        "ix_account_password_reset_tokens_email_requested",
        table_name="account_password_reset_tokens",
    )
    op.drop_table("account_password_reset_tokens")
