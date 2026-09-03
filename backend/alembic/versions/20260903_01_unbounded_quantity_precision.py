"""Remove generic scale limits from semantic quantity columns.

Revision ID: 20260903_01
Revises: 20260902_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260903_01"
down_revision = "20260902_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "purchase_import_lines",
        "quantity_raw",
        existing_type=sa.Numeric(precision=10, scale=2),
        type_=sa.Numeric(),
        existing_nullable=False,
    )
    op.alter_column(
        "receipt_table_lines",
        "quantity",
        existing_type=sa.Numeric(precision=12, scale=3),
        type_=sa.Numeric(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "receipt_table_lines",
        "quantity",
        existing_type=sa.Numeric(),
        type_=sa.Numeric(precision=12, scale=3),
        existing_nullable=True,
    )
    op.alter_column(
        "purchase_import_lines",
        "quantity_raw",
        existing_type=sa.Numeric(),
        type_=sa.Numeric(precision=10, scale=2),
        existing_nullable=False,
    )
