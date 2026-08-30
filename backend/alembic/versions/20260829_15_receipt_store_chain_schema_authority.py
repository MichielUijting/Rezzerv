"""Move residual receipt store-chain schema authority to Alembic.

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


def _columns(bind: sa.engine.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(_RECEIPT_TABLE)
    }


def _ensure_store_chain(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_RECEIPT_TABLE):
        raise RuntimeError("Canonical receipt_tables ontbreekt vóór receipt store-chain authority")

    columns = _columns(bind)
    if "store_chain" not in columns:
        op.add_column(
            _RECEIPT_TABLE,
            sa.Column("store_chain", sa.Text(), nullable=True),
        )
        columns = _columns(bind)

    column_type = columns["store_chain"]["type"]
    if not isinstance(column_type, (sa.Text, sa.String)):
        raise RuntimeError(
            "Canonical receipt_tables.store_chain moet een tekstkolom zijn; "
            f"gevonden type={column_type}"
        )


def upgrade() -> None:
    _ensure_store_chain(op.get_bind())


def downgrade() -> None:
    # Existing SQLite installations may already contain store_chain because the
    # legacy runtime helper created it before this authority cutover. Dropping
    # the column would therefore be destructive and is intentionally omitted.
    pass
