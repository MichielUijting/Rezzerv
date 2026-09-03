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


# These are the two exact legacy production rows whose original quantities were
# proven before the erroneous 2-decimal normalization was introduced. Repair
# only when the row still contains that exact rounded value, so later user
# edits are never overwritten.
_GUARDED_QUANTITY_REPAIRS = (
    ("239ccbf1-6880-4390-9c83-cb141836f72c", "0.40", "0.404"),
    ("572f88a8-1bca-4e47-ac8c-0d903188ca4b", "1.22", "1.224"),
)


def _restore_proven_rounded_quantities() -> None:
    connection = op.get_bind()
    for line_id, rounded_value, original_value in _GUARDED_QUANTITY_REPAIRS:
        connection.execute(
            sa.text(
                "UPDATE purchase_import_lines "
                f"SET quantity_raw = {original_value} "
                "WHERE id = :line_id "
                f"AND quantity_raw = {rounded_value}"
            ),
            {"line_id": line_id},
        )


def upgrade() -> None:
    with op.batch_alter_table("purchase_import_lines") as batch_op:
        batch_op.alter_column(
            "quantity_raw",
            existing_type=sa.Numeric(precision=10, scale=2),
            type_=sa.Numeric(),
            existing_nullable=False,
        )
    with op.batch_alter_table("receipt_table_lines") as batch_op:
        batch_op.alter_column(
            "quantity",
            existing_type=sa.Numeric(precision=12, scale=3),
            type_=sa.Numeric(),
            existing_nullable=True,
        )
    _restore_proven_rounded_quantities()


def downgrade() -> None:
    with op.batch_alter_table("receipt_table_lines") as batch_op:
        batch_op.alter_column(
            "quantity",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(precision=12, scale=3),
            existing_nullable=True,
        )
    with op.batch_alter_table("purchase_import_lines") as batch_op:
        batch_op.alter_column(
            "quantity_raw",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(precision=10, scale=2),
            existing_nullable=False,
        )
