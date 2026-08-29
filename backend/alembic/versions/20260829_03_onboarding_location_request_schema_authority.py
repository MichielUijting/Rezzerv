"""Move onboarding and location request schema authority to Alembic.

Revision ID: 20260829_03
Revises: 20260829_02
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_03"
down_revision: Union[str, None] = "20260829_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ONBOARDING = "household_onboarding"
_REGISTRY = "household_registry"
_SPACES = "spaces"
_SUBLOCATIONS = "sublocations"
_ONBOARDING_COLUMNS = {
    "household_id",
    "onboarding_status",
    "onboarding_version",
    "primary_use_case",
    "onboarding_step",
    "household_usage_mode",
    "onboarding_completed_at",
    "created_at",
    "updated_at",
}
_SPACE_COLUMNS = {"id", "naam", "household_id", "active"}
_SUBLOCATION_COLUMNS = {"id", "naam", "space_id", "active"}


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _registry_id_column(bind: sa.engine.Connection) -> str:
    columns = _columns(bind, _REGISTRY)
    if "id" in columns:
        return "id"
    if "household_id" in columns:
        return "household_id"
    raise RuntimeError("household_registry heeft geen bruikbare identificatiekolom")


def _backfill_existing_households(bind: sa.engine.Connection) -> None:
    registry_columns = _columns(bind, _REGISTRY)
    household_id_column = _registry_id_column(bind)
    if "context_type" in registry_columns:
        regular_predicate = "lower(trim(COALESCE(hr.context_type, 'regular'))) = 'regular'"
    else:
        regular_predicate = f"CAST(hr.{household_id_column} AS TEXT) <> '0'"

    bind.execute(
        sa.text(
            f"""
            INSERT INTO household_onboarding (
                household_id,
                onboarding_status,
                onboarding_version,
                primary_use_case,
                onboarding_step,
                household_usage_mode,
                onboarding_completed_at,
                created_at,
                updated_at
            )
            SELECT
                CAST(hr.{household_id_column} AS TEXT),
                'completed',
                2,
                NULL,
                NULL,
                NULL,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM household_registry hr
            WHERE {regular_predicate}
              AND NOT EXISTS (
                  SELECT 1
                  FROM household_onboarding ho
                  WHERE ho.household_id = CAST(hr.{household_id_column} AS TEXT)
              )
            """
        )
    )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    for table_name in (_REGISTRY, _ONBOARDING, _SPACES, _SUBLOCATIONS):
        if not inspector.has_table(table_name):
            raise RuntimeError(f"Canonical onboarding/location tabel ontbreekt: {table_name}")
    missing_onboarding = _ONBOARDING_COLUMNS - _columns(bind, _ONBOARDING)
    if missing_onboarding:
        raise RuntimeError(
            f"household_onboarding mist canonical kolommen: {sorted(missing_onboarding)}"
        )
    missing_spaces = _SPACE_COLUMNS - _columns(bind, _SPACES)
    if missing_spaces:
        raise RuntimeError(f"spaces mist canonical kolommen: {sorted(missing_spaces)}")
    missing_sublocations = _SUBLOCATION_COLUMNS - _columns(bind, _SUBLOCATIONS)
    if missing_sublocations:
        raise RuntimeError(
            f"sublocations mist canonical kolommen: {sorted(missing_sublocations)}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table(_REGISTRY):
        raise RuntimeError("household_registry ontbreekt; onboarding authority kan niet worden geadopteerd")

    if not inspector.has_table(_ONBOARDING):
        op.create_table(
            _ONBOARDING,
            sa.Column("household_id", sa.Text(), primary_key=True),
            sa.Column("onboarding_status", sa.Text(), nullable=False),
            sa.Column("onboarding_version", sa.Integer(), nullable=False, server_default=sa.text("2")),
            sa.Column("primary_use_case", sa.Text(), nullable=True),
            sa.Column("onboarding_step", sa.Text(), nullable=True),
            sa.Column("household_usage_mode", sa.Text(), nullable=True),
            sa.Column("onboarding_completed_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint(
                "onboarding_status IN ('not_started', 'in_progress', 'completed')",
                name="ck_household_onboarding_status",
            ),
            sa.CheckConstraint(
                "primary_use_case IS NULL OR primary_use_case IN ('inhuis_halen', 'wat_inhuis', 'waar_inhuis')",
                name="ck_household_onboarding_primary_use_case",
            ),
            sa.CheckConstraint(
                "household_usage_mode IS NULL OR household_usage_mode IN ('alone', 'together')",
                name="ck_household_onboarding_usage_mode",
            ),
        )
    else:
        onboarding_columns = _columns(bind, _ONBOARDING)
        required_legacy = _ONBOARDING_COLUMNS - {"household_usage_mode"}
        missing_legacy = required_legacy - onboarding_columns
        if missing_legacy:
            raise RuntimeError(
                f"household_onboarding legacy contract mist kolommen: {sorted(missing_legacy)}"
            )
        if "household_usage_mode" not in onboarding_columns:
            op.add_column(_ONBOARDING, sa.Column("household_usage_mode", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    if not inspector.has_table(_SPACES):
        op.create_table(
            _SPACES,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("naam", sa.Text(), nullable=False),
            sa.Column("household_id", sa.Text(), nullable=True),
            sa.Column("active", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    else:
        columns = _columns(bind, _SPACES)
        required_legacy = {"id", "naam"}
        missing_legacy = required_legacy - columns
        if missing_legacy:
            raise RuntimeError(f"spaces legacy contract mist kolommen: {sorted(missing_legacy)}")
        if "household_id" not in columns:
            op.add_column(_SPACES, sa.Column("household_id", sa.Text(), nullable=True))
        if "active" not in columns:
            op.add_column(
                _SPACES,
                sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            )
            bind.execute(sa.text("UPDATE spaces SET active = 1 WHERE active IS NULL"))

    inspector = sa.inspect(bind)
    if not inspector.has_table(_SUBLOCATIONS):
        op.create_table(
            _SUBLOCATIONS,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("naam", sa.Text(), nullable=False),
            sa.Column("space_id", sa.Text(), nullable=True),
            sa.Column("active", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    else:
        columns = _columns(bind, _SUBLOCATIONS)
        required_legacy = {"id", "naam"}
        missing_legacy = required_legacy - columns
        if missing_legacy:
            raise RuntimeError(
                f"sublocations legacy contract mist kolommen: {sorted(missing_legacy)}"
            )
        if "space_id" not in columns:
            op.add_column(_SUBLOCATIONS, sa.Column("space_id", sa.Text(), nullable=True))
        if "active" not in columns:
            op.add_column(
                _SUBLOCATIONS,
                sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            )
            bind.execute(sa.text("UPDATE sublocations SET active = 1 WHERE active IS NULL"))

    _backfill_existing_households(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The onboarding/location request schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
