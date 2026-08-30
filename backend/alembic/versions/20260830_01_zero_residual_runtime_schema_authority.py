"""Move final residual runtime schema authority to Alembic.

Revision ID: 20260830_01
Revises: 20260829_15
Create Date: 2026-08-30
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_01"
down_revision: Union[str, None] = "20260829_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LINE_OVERRIDE_TABLE = "purchase_import_line_inventory_handling_overrides"
_WEBHOOK_DELIVERY_TABLE = "receipt_webhook_deliveries"

_LINE_OVERRIDE_COLUMNS = {
    "purchase_import_line_id",
    "household_id",
    "inventory_handling",
    "updated_by_user_id",
    "updated_at",
}
_WEBHOOK_DELIVERY_COLUMNS = {
    "svix_id",
    "svix_timestamp",
    "payload_sha256",
    "status",
    "created_at",
    "updated_at",
}


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    return sa.Text()


def _columns(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _primary_key(bind: sa.engine.Connection, table_name: str) -> tuple[str, ...]:
    return tuple(
        str(column or "")
        for column in (
            sa.inspect(bind).get_pk_constraint(table_name).get("constrained_columns") or ()
        )
    )


def _normalize_postgresql_timestamp(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> None:
    column = _columns(bind, table_name)[column_name]
    column_type = column["type"]
    if isinstance(column_type, sa.DateTime) and bool(getattr(column_type, "timezone", False)):
        return
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'
    )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
        f'TYPE TIMESTAMPTZ USING "{column_name}"::text::timestamptz'
    )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
        "SET DEFAULT CURRENT_TIMESTAMP"
    )


def _ensure_line_override_table(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LINE_OVERRIDE_TABLE):
        op.create_table(
            _LINE_OVERRIDE_TABLE,
            sa.Column("purchase_import_line_id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("inventory_handling", sa.Text(), nullable=True),
            sa.Column("updated_by_user_id", sa.Text(), nullable=True),
            sa.Column(
                "updated_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "inventory_handling IS NULL OR "
                "inventory_handling IN ('STOCK', 'DIRECT_CONSUMPTION')",
                name="ck_purchase_import_line_inventory_handling_override_value",
            ),
        )
    else:
        columns = _columns(bind, _LINE_OVERRIDE_TABLE)
        missing = _LINE_OVERRIDE_COLUMNS - set(columns)
        if missing:
            raise RuntimeError(
                f"{_LINE_OVERRIDE_TABLE} mist canonical kolommen: {sorted(missing)}"
            )
        if _primary_key(bind, _LINE_OVERRIDE_TABLE) != ("purchase_import_line_id",):
            raise RuntimeError(
                f"{_LINE_OVERRIDE_TABLE} heeft geen canonical primary key"
            )
        invalid = bind.execute(
            sa.text(
                f"SELECT inventory_handling FROM {_LINE_OVERRIDE_TABLE} "
                "WHERE inventory_handling IS NOT NULL "
                "AND inventory_handling NOT IN ('STOCK', 'DIRECT_CONSUMPTION') LIMIT 1"
            )
        ).first()
        if invalid is not None:
            raise RuntimeError(
                f"{_LINE_OVERRIDE_TABLE} bevat ongeldige inventory_handling waarden"
            )
        if bind.dialect.name == "postgresql":
            _normalize_postgresql_timestamp(bind, _LINE_OVERRIDE_TABLE, "updated_at")

    columns = _columns(bind, _LINE_OVERRIDE_TABLE)
    if set(columns) < _LINE_OVERRIDE_COLUMNS:
        raise RuntimeError(f"Canonical {_LINE_OVERRIDE_TABLE} contract ontbreekt na migratie")
    if bool(columns["household_id"].get("nullable")):
        raise RuntimeError(f"{_LINE_OVERRIDE_TABLE}.household_id moet NOT NULL zijn")
    if bool(columns["updated_at"].get("nullable")):
        raise RuntimeError(f"{_LINE_OVERRIDE_TABLE}.updated_at moet NOT NULL zijn")
    if bind.dialect.name == "postgresql":
        updated_at = columns["updated_at"]["type"]
        if not isinstance(updated_at, sa.DateTime) or not bool(
            getattr(updated_at, "timezone", False)
        ):
            raise RuntimeError(
                f"{_LINE_OVERRIDE_TABLE}.updated_at moet TIMESTAMPTZ zijn; actual={updated_at}"
            )


def _ensure_webhook_delivery_table(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_WEBHOOK_DELIVERY_TABLE):
        op.create_table(
            _WEBHOOK_DELIVERY_TABLE,
            sa.Column("svix_id", sa.Text(), primary_key=True),
            sa.Column("svix_timestamp", sa.Integer(), nullable=False),
            sa.Column("payload_sha256", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'processing'"),
            ),
            sa.Column(
                "created_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    else:
        columns = _columns(bind, _WEBHOOK_DELIVERY_TABLE)
        missing = _WEBHOOK_DELIVERY_COLUMNS - set(columns)
        if missing:
            raise RuntimeError(
                f"{_WEBHOOK_DELIVERY_TABLE} mist canonical kolommen: {sorted(missing)}"
            )
        if _primary_key(bind, _WEBHOOK_DELIVERY_TABLE) != ("svix_id",):
            raise RuntimeError(
                f"{_WEBHOOK_DELIVERY_TABLE} heeft geen canonical primary key"
            )
        if bind.dialect.name == "postgresql":
            _normalize_postgresql_timestamp(bind, _WEBHOOK_DELIVERY_TABLE, "created_at")
            _normalize_postgresql_timestamp(bind, _WEBHOOK_DELIVERY_TABLE, "updated_at")

    columns = _columns(bind, _WEBHOOK_DELIVERY_TABLE)
    if set(columns) < _WEBHOOK_DELIVERY_COLUMNS:
        raise RuntimeError(f"Canonical {_WEBHOOK_DELIVERY_TABLE} contract ontbreekt na migratie")
    for column_name in ("svix_timestamp", "payload_sha256", "status", "created_at", "updated_at"):
        if bool(columns[column_name].get("nullable")):
            raise RuntimeError(
                f"{_WEBHOOK_DELIVERY_TABLE}.{column_name} moet NOT NULL zijn"
            )
    if bind.dialect.name == "postgresql":
        for column_name in ("created_at", "updated_at"):
            column_type = columns[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise RuntimeError(
                    f"{_WEBHOOK_DELIVERY_TABLE}.{column_name} moet TIMESTAMPTZ zijn; "
                    f"actual={column_type}"
                )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    _ensure_line_override_table(bind)
    _ensure_webhook_delivery_table(bind)


def downgrade() -> None:
    # These tables may predate this revision because legacy runtime request and
    # startup paths created them. Dropping them would destroy user overrides or
    # webhook idempotency history, so authority adoption is non-destructive.
    pass
