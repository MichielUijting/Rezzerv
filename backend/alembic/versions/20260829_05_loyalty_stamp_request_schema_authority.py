"""Move loyalty-stamp request schema under Alembic authority.

Revision ID: 20260829_05
Revises: 20260829_04
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_05"
down_revision: Union[str, None] = "20260829_04"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


REQUIRED_COLUMNS = {
    "id",
    "household_id",
    "receipt_table_id",
    "receipt_line_id",
    "store_name",
    "stamp_program_code",
    "quantity",
    "unit_price",
    "line_total",
    "transaction_type",
    "source",
    "purchase_at",
    "created_at",
    "updated_at",
}


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _index_names(bind, table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()

    if "loyalty_stamp_transactions" not in _table_names(bind):
        op.create_table(
            "loyalty_stamp_transactions",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("receipt_table_id", sa.Text(), nullable=False),
            sa.Column("receipt_line_id", sa.Text(), nullable=False),
            sa.Column("store_name", sa.Text(), nullable=True),
            sa.Column("stamp_program_code", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("unit_price", sa.Float(), nullable=True),
            sa.Column("line_total", sa.Float(), nullable=True),
            sa.Column(
                "transaction_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'purchase'"),
            ),
            sa.Column(
                "source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'receipt_table_line'"),
            ),
            sa.Column("purchase_at", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.Text(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.Text(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    else:
        missing = REQUIRED_COLUMNS - _column_names(
            bind, "loyalty_stamp_transactions"
        )
        if missing:
            raise RuntimeError(
                "Cannot adopt loyalty_stamp_transactions: missing required columns: "
                + ", ".join(sorted(missing))
            )

    # Protect creation of the unique receipt-line index when historical data
    # predates that invariant. The newest row remains authoritative.
    op.execute(
        sa.text(
            """
            DELETE FROM loyalty_stamp_transactions
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY receipt_line_id
                            ORDER BY COALESCE(updated_at, created_at, '') DESC,
                                     created_at DESC,
                                     id DESC
                        ) AS receipt_line_rank
                    FROM loyalty_stamp_transactions
                ) ranked
                WHERE receipt_line_rank > 1
            )
            """
        )
    )

    indexes = _index_names(bind, "loyalty_stamp_transactions")
    if "idx_loyalty_stamp_transactions_receipt_line" not in indexes:
        op.create_index(
            "idx_loyalty_stamp_transactions_receipt_line",
            "loyalty_stamp_transactions",
            ["receipt_line_id"],
            unique=True,
        )
    if "idx_loyalty_stamp_transactions_household_store" not in indexes:
        op.create_index(
            "idx_loyalty_stamp_transactions_household_store",
            "loyalty_stamp_transactions",
            ["household_id", "store_name", "purchase_at"],
            unique=False,
        )
    if "idx_loyalty_stamp_transactions_receipt_table" not in indexes:
        op.create_index(
            "idx_loyalty_stamp_transactions_receipt_table",
            "loyalty_stamp_transactions",
            ["receipt_table_id"],
            unique=False,
        )


def downgrade() -> None:
    # Adoption migration: preserve pre-existing loyalty data and indexes rather
    # than guessing which objects Alembic originally created.
    pass
