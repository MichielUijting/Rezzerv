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
    "actor_user_id",
    "attribution_source",
    "first_attributed_at",
    "last_attributed_at",
}
_INDEX = "idx_actor_object_attributions_household_actor"
_INDEX_COLUMNS = ("household_id", "actor_user_id", "object_type")


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError(f"{_TABLE} ontbreekt")
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(_TABLE)
    }
    missing = _REQUIRED_COLUMNS - set(columns)
    if missing:
        raise RuntimeError(f"{_TABLE} mist canonieke kolommen: {sorted(missing)}")
    for column_name in _REQUIRED_COLUMNS:
        if bool(columns[column_name].get("nullable")):
            raise RuntimeError(f"{_TABLE}.{column_name} moet NOT NULL zijn")
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
    index = indexes.get(_INDEX)
    actual_columns = tuple((index or {}).get("column_names") or ())
    if not index or actual_columns != _INDEX_COLUMNS or bool(index.get("unique")):
        raise RuntimeError(
            f"{_TABLE}.{_INDEX} wijkt af: expected={_INDEX_COLUMNS!r} "
            f"actual={actual_columns!r} unique={bool((index or {}).get('unique'))}"
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
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("actor_user_id", sa.Text(), nullable=False),
            sa.Column(
                "attribution_source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'runtime_session'"),
            ),
            sa.Column("first_attributed_at", sa.Text(), nullable=False),
            sa.Column("last_attributed_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("object_type", "object_id"),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_TABLE)
    }
    existing = existing_indexes.get(_INDEX)
    if existing is None:
        op.create_index(_INDEX, _TABLE, list(_INDEX_COLUMNS), unique=False)
    else:
        actual_columns = tuple(existing.get("column_names") or ())
        if actual_columns != _INDEX_COLUMNS or bool(existing.get("unique")):
            raise RuntimeError(
                f"Bestaande {_INDEX} wijkt af van canonical actor attribution contract"
            )

    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The actor-attribution schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
