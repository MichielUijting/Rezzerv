"""Move household product use-case schema authority to Alembic.

Revision ID: 20260829_10
Revises: 20260829_09
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_10"
down_revision: Union[str, None] = "20260829_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "household_product_use_cases"
_REQUIRED_COLUMNS = {"household_id", "use_case", "activated_at"}


def _columns(bind: sa.engine.Connection) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in sa.inspect(bind).get_columns(_TABLE)
    }


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError(f"Canonical gebruiksdoeltabel ontbreekt: {_TABLE}")
    missing = _REQUIRED_COLUMNS - _columns(bind)
    if missing:
        raise RuntimeError(
            f"{_TABLE} mist canonical kolommen: {sorted(missing)}"
        )
    primary_key = tuple(
        inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("household_id", "use_case"):
        raise RuntimeError(
            f"{_TABLE} heeft onjuiste primary key: {primary_key!r}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("use_case", sa.Text(), nullable=False),
            sa.Column(
                "activated_at",
                sa.Text(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("household_id", "use_case"),
            sa.CheckConstraint(
                "use_case IN ('inhuis_halen', 'wat_inhuis', 'waar_inhuis')",
                name="ck_household_product_use_cases_use_case",
            ),
        )

    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The household product use-case schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
