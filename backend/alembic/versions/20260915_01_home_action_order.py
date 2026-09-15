"""Persist global Startpagina action ordering.

Revision ID: 20260915_01
Revises: 20260908_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260915_01"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    inspector = sa.inspect(bind)
    if inspector.has_table("platform_home_action_order"):
        return
    op.create_table(
        "platform_home_action_order",
        sa.Column("flag_key", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("flag_key", name="pk_platform_home_action_order"),
        sa.UniqueConstraint("sort_order", name="uq_platform_home_action_order_sort_order"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    if sa.inspect(bind).has_table("platform_home_action_order"):
        op.drop_table("platform_home_action_order")
