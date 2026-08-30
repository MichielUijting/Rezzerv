"""Move residual receipt status schema authority to Alembic.

Revision ID: 20260829_15
Revises: 20260829_14
Create Date: 2026-08-30
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_15"
down_revision: Union[str, None] = "20260829_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RECEIPT_TABLE = "receipt_tables"
_RECEIPT_LINE_TABLE = "receipt_table_lines"
_RECEIPT_SOURCE_TABLE = "receipt_sources"


def _columns(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _assert_table(bind: sa.engine.Connection, table_name: str) -> None:
    if not sa.inspect(bind).has_table(table_name):
        raise RuntimeError(f"Canonical receipt table ontbreekt: {table_name}")


def _ensure_store_chain(bind: sa.engine.Connection) -> None:
    _assert_table(bind, _RECEIPT_TABLE)
    columns = _columns(bind, _RECEIPT_TABLE)
    if "store_chain" not in columns:
        op.add_column(_RECEIPT_TABLE, sa.Column("store_chain", sa.Text(), nullable=True))
        columns = _columns(bind, _RECEIPT_TABLE)
    column_type = columns["store_chain"]["type"]
    if not isinstance(column_type, (sa.Text, sa.String)):
        raise RuntimeError(
            f"Canonical receipt_tables.store_chain moet tekst zijn, kreeg {column_type}"
        )


def _assert_postgresql_booleans(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    expected = {
        _RECEIPT_LINE_TABLE: ("is_deleted", "is_validated"),
        _RECEIPT_SOURCE_TABLE: ("is_active",),
    }
    for table_name, column_names in expected.items():
        _assert_table(bind, table_name)
        columns = _columns(bind, table_name)
        for column_name in column_names:
            if column_name not in columns:
                raise RuntimeError(
                    f"Canonical receipt Boolean ontbreekt: {table_name}.{column_name}"
                )
            if not isinstance(columns[column_name]["type"], sa.Boolean):
                raise RuntimeError(
                    f"Canonical receipt Boolean wijkt af: {table_name}.{column_name} "
                    f"type={columns[column_name]['type']}"
                )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_store_chain(bind)
    _assert_postgresql_booleans(bind)


def downgrade() -> None:
    # store_chain predates this authority cutover on some installations and may
    # contain user-visible status-baseline data. Do not destructively drop it.
    pass
