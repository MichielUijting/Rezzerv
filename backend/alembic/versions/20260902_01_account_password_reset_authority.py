"""Add Alembic-owned account password reset token authority.

Revision ID: 20260902_01
Revises: 20260830_02
Create Date: 2026-09-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260902_01"
down_revision: Union[str, None] = "20260830_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "account_password_reset_tokens"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("request_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("token_hash", name="uq_account_password_reset_token_hash"),
    )
    op.create_index(
        "idx_account_password_reset_user_requested",
        _TABLE,
        ["user_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "idx_account_password_reset_ip_requested",
        _TABLE,
        ["request_ip_hash", "requested_at"],
        unique=False,
    )
    op.create_index(
        "idx_account_password_reset_active",
        _TABLE,
        ["token_hash", "expires_at", "used_at", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_account_password_reset_active", table_name=_TABLE)
    op.drop_index("idx_account_password_reset_ip_requested", table_name=_TABLE)
    op.drop_index("idx_account_password_reset_user_requested", table_name=_TABLE)
    op.drop_table(_TABLE)
