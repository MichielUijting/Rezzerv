"""Move actor attribution schema authority to Alembic.

Revision ID: 20260828_05
Revises: 20260828_04
Create Date: 2026-08-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_05"
down_revision: Union[str, None] = "20260828_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "actor_object_attributions"
_REQUIRED_COLUMNS = {
    "object_type",
    "object_id",
    "household_id",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
}
_INDEXES = {
    "idx_actor_attribution_household": ("household_id", "object_type"),
    "idx_actor_attribution_created_by": ("created_by_user_id",),
    "idx_actor_attribution_updated_by": ("updated_by_user_id",),
}


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError(f"{_TABLE} ontbreekt")
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_TABLE)
    }
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise RuntimeError(f"{_TABLE} mist canonieke kolommen: {sorted(missing)}")
    primary_key = tuple(
        str(column or "")
        for column in (inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ())
    )
    if primary_key != ("object_type", "object_id"):
        raise RuntimeError(
            f"{_TABLE} heeft onjuiste primaire sleutel: {primary_key!r}"
        )
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_TABLE)
    }
    for index_name, expected_columns in _INDEXES.items():
        index = indexes.get(index_name)
        actual_columns = tuple((index or {}).get("column_names") or ())
        if not index or actual_columns != expected_columns or bool(index.get("unique")):
            raise RuntimeError(
                f"{_TABLE}.{index_name} wijkt af: "
                f"expected={expected_columns!r} actual={actual_columns!r} "
                f"unique={bool((index or {}).get('unique'))}"
            )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("object_type", sa.Text(), nullable=False),
            sa.Column("object_id", sa.Text(), nullable=False),
            sa.Column("household_id", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.Text(), nullable=True),
            sa.Column("updated_by_user_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("object_type", "object_id"),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_TABLE)
    }
    for index_name, columns in _INDEXES.items():
        existing = existing_indexes.get(index_name)
        if existing is None:
            op.create_index(index_name, _TABLE, list(columns), unique=False)
        else:
            actual_columns = tuple(existing.get("column_names") or ())
            if actual_columns != columns or bool(existing.get("unique")):
                raise RuntimeError(
                    f"Bestaande {index_name} wijkt af van canonical actor attribution contract"
                )

    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The actor-attribution schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
