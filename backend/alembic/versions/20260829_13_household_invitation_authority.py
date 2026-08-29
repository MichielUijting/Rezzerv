"""Move household invitation lifecycle and delivery schema authority to Alembic.

Revision ID: 20260829_13
Revises: 20260829_12
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_13"
down_revision: Union[str, None] = "20260829_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "household_invitations"
_PENDING_INDEX = "idx_household_invitations_one_pending"
_STATUS_INDEX = "idx_household_invitations_household_status"
_EXPIRY_INDEX = "idx_household_invitations_expiry"
_ROLE_CHECK = "ck_household_invitations_role_key"
_STATUS_CHECK = "ck_household_invitations_status"
_DELIVERY_CHECK = "ck_household_invitations_delivery_status"

_REQUIRED_COLUMNS = {
    "id",
    "household_id",
    "invitee_email",
    "role_key",
    "token_hash",
    "status",
    "expires_at",
    "created_by_user_id",
    "accepted_by_user_id",
    "created_at",
    "updated_at",
    "accepted_at",
    "revoked_at",
    "delivery_status",
    "delivery_attempt_count",
    "last_delivery_attempt_at",
    "last_delivered_at",
    "last_delivery_error",
    "delivery_provider_message_id",
    "last_delivery_actor_user_id",
}
_TIMESTAMP_COLUMNS = {
    "expires_at": False,
    "created_at": False,
    "updated_at": False,
    "accepted_at": True,
    "revoked_at": True,
    "last_delivery_attempt_at": True,
    "last_delivered_at": True,
}


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    return sa.Text()


def _columns(bind: sa.engine.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(_TABLE)
    }


def _indexes(bind: sa.engine.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(_TABLE)
    }


def _checks(bind: sa.engine.Connection) -> set[str]:
    return {
        str(check.get("name") or "")
        for check in sa.inspect(bind).get_check_constraints(_TABLE)
        if check.get("name")
    }


def _normalize_postgresql_timestamp(
    bind: sa.engine.Connection,
    column_name: str,
    *,
    nullable: bool,
    default_current_timestamp: bool = False,
) -> None:
    column = _columns(bind)[column_name]
    if isinstance(column["type"], sa.DateTime) and bool(
        getattr(column["type"], "timezone", False)
    ):
        return
    bind.exec_driver_sql(
        f'ALTER TABLE "{_TABLE}" ALTER COLUMN "{column_name}" DROP DEFAULT'
    )
    if nullable:
        using = (
            f"CASE WHEN NULLIF(trim(\"{column_name}\"::text), '') IS NULL "
            f"THEN NULL ELSE \"{column_name}\"::text::timestamptz END"
        )
    else:
        using = f'"{column_name}"::text::timestamptz'
    bind.exec_driver_sql(
        f'ALTER TABLE "{_TABLE}" ALTER COLUMN "{column_name}" '
        f"TYPE TIMESTAMPTZ USING {using}"
    )
    if default_current_timestamp:
        bind.exec_driver_sql(
            f'ALTER TABLE "{_TABLE}" ALTER COLUMN "{column_name}" '
            "SET DEFAULT CURRENT_TIMESTAMP"
        )


def _create_table(bind: sa.engine.Connection) -> None:
    timestamp = _timestamp_type(bind.dialect.name)
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("invitee_email", sa.Text(), nullable=False),
        sa.Column("role_key", sa.Text(), nullable=False, server_default=sa.text("'household.member'")),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.Column("accepted_at", timestamp, nullable=True),
        sa.Column("revoked_at", timestamp, nullable=True),
        sa.Column("delivery_status", sa.Text(), nullable=False, server_default=sa.text("'not_sent'")),
        sa.Column("delivery_attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_delivery_attempt_at", timestamp, nullable=True),
        sa.Column("last_delivered_at", timestamp, nullable=True),
        sa.Column("last_delivery_error", sa.Text(), nullable=True),
        sa.Column("delivery_provider_message_id", sa.Text(), nullable=True),
        sa.Column("last_delivery_actor_user_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_household_invitations_token_hash"),
        sa.CheckConstraint("role_key = 'household.member'", name=_ROLE_CHECK),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name=_STATUS_CHECK,
        ),
        sa.CheckConstraint(
            "delivery_status IN ('not_sent', 'sent', 'failed', 'disabled', 'config_invalid')",
            name=_DELIVERY_CHECK,
        ),
    )


def _adopt_existing_table(bind: sa.engine.Connection) -> None:
    columns = _columns(bind)
    required_lifecycle = {
        "id",
        "household_id",
        "invitee_email",
        "role_key",
        "token_hash",
        "status",
        "expires_at",
        "created_by_user_id",
        "accepted_by_user_id",
        "created_at",
        "updated_at",
        "accepted_at",
        "revoked_at",
    }
    missing_lifecycle = required_lifecycle - set(columns)
    if missing_lifecycle:
        raise RuntimeError(
            "Bestaande household_invitations wijkt af van het canonical lifecycle-contract: "
            f"ontbrekend={sorted(missing_lifecycle)}"
        )

    additions: tuple[sa.Column[Any], ...] = (
        sa.Column("delivery_status", sa.Text(), nullable=False, server_default=sa.text("'not_sent'")),
        sa.Column("delivery_attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_delivery_attempt_at", _timestamp_type(bind.dialect.name), nullable=True),
        sa.Column("last_delivered_at", _timestamp_type(bind.dialect.name), nullable=True),
        sa.Column("last_delivery_error", sa.Text(), nullable=True),
        sa.Column("delivery_provider_message_id", sa.Text(), nullable=True),
        sa.Column("last_delivery_actor_user_id", sa.Text(), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column(_TABLE, column)
            columns = _columns(bind)

    invalid_role = bind.execute(
        sa.text(
            "SELECT DISTINCT role_key FROM household_invitations "
            "WHERE role_key <> 'household.member' OR role_key IS NULL"
        )
    ).all()
    if invalid_role:
        raise RuntimeError(
            f"household_invitations bevat ongeldige role_key waarden: {[row[0] for row in invalid_role]!r}"
        )
    invalid_status = bind.execute(
        sa.text(
            "SELECT DISTINCT status FROM household_invitations "
            "WHERE status NOT IN ('pending', 'accepted', 'revoked', 'expired') OR status IS NULL"
        )
    ).all()
    if invalid_status:
        raise RuntimeError(
            f"household_invitations bevat ongeldige statuswaarden: {[row[0] for row in invalid_status]!r}"
        )
    invalid_delivery = bind.execute(
        sa.text(
            "SELECT DISTINCT delivery_status FROM household_invitations "
            "WHERE delivery_status NOT IN ('not_sent', 'sent', 'failed', 'disabled', 'config_invalid') "
            "OR delivery_status IS NULL"
        )
    ).all()
    if invalid_delivery:
        raise RuntimeError(
            "household_invitations bevat ongeldige delivery_status waarden: "
            f"{[row[0] for row in invalid_delivery]!r}"
        )

    if bind.dialect.name == "postgresql":
        for column_name, nullable in _TIMESTAMP_COLUMNS.items():
            _normalize_postgresql_timestamp(
                bind,
                column_name,
                nullable=nullable,
            )
        op.alter_column(
            _TABLE,
            "role_key",
            existing_type=sa.Text(),
            nullable=False,
            server_default=sa.text("'household.member'"),
        )
        op.alter_column(
            _TABLE,
            "status",
            existing_type=sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        )
        op.alter_column(
            _TABLE,
            "delivery_status",
            existing_type=sa.Text(),
            nullable=False,
            server_default=sa.text("'not_sent'"),
        )
        op.alter_column(
            _TABLE,
            "delivery_attempt_count",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )

        checks = _checks(bind)
        if _ROLE_CHECK not in checks:
            op.create_check_constraint(_ROLE_CHECK, _TABLE, "role_key = 'household.member'")
        checks = _checks(bind)
        if _STATUS_CHECK not in checks:
            op.create_check_constraint(
                _STATUS_CHECK,
                _TABLE,
                "status IN ('pending', 'accepted', 'revoked', 'expired')",
            )
        checks = _checks(bind)
        if _DELIVERY_CHECK not in checks:
            op.create_check_constraint(
                _DELIVERY_CHECK,
                _TABLE,
                "delivery_status IN ('not_sent', 'sent', 'failed', 'disabled', 'config_invalid')",
            )


def _ensure_indexes(bind: sa.engine.Connection) -> None:
    indexes = _indexes(bind)
    if _PENDING_INDEX not in indexes:
        op.create_index(
            _PENDING_INDEX,
            _TABLE,
            ["household_id", "invitee_email"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
            sqlite_where=sa.text("status = 'pending'"),
        )
    indexes = _indexes(bind)
    if _STATUS_INDEX not in indexes:
        op.create_index(
            _STATUS_INDEX,
            _TABLE,
            ["household_id", "status", "created_at"],
            unique=False,
        )
    indexes = _indexes(bind)
    if _EXPIRY_INDEX not in indexes:
        op.create_index(
            _EXPIRY_INDEX,
            _TABLE,
            ["status", "expires_at"],
            unique=False,
        )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError(f"Canonical invitation table ontbreekt: {_TABLE}")
    columns = _columns(bind)
    missing = _REQUIRED_COLUMNS - set(columns)
    if missing:
        raise RuntimeError(f"{_TABLE} mist canonical kolommen: {sorted(missing)}")

    primary_key = tuple(
        inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("id",):
        raise RuntimeError(f"{_TABLE} heeft onjuiste primary key: {primary_key!r}")

    token_unique = any(
        tuple(item.get("column_names") or ()) == ("token_hash",)
        for item in inspector.get_unique_constraints(_TABLE)
    )
    if not token_unique:
        # SQLite may report an auto-index through get_indexes rather than named unique constraints.
        token_unique = any(
            bool(item.get("unique"))
            and tuple(item.get("column_names") or ()) == ("token_hash",)
            for item in inspector.get_indexes(_TABLE)
        )
    if not token_unique:
        raise RuntimeError(f"{_TABLE}.token_hash moet uniek zijn")

    indexes = _indexes(bind)
    expected_indexes = {
        _PENDING_INDEX: ("household_id", "invitee_email"),
        _STATUS_INDEX: ("household_id", "status", "created_at"),
        _EXPIRY_INDEX: ("status", "expires_at"),
    }
    for index_name, expected_columns in expected_indexes.items():
        index = indexes.get(index_name)
        actual_columns = tuple((index or {}).get("column_names") or ())
        if index is None or actual_columns != expected_columns:
            raise RuntimeError(
                f"Invalid {index_name}: expected={expected_columns!r} actual={actual_columns!r}"
            )
    if not bool(indexes[_PENDING_INDEX].get("unique")):
        raise RuntimeError(f"{_PENDING_INDEX} moet uniek zijn")

    if bind.dialect.name == "postgresql":
        for column_name in _TIMESTAMP_COLUMNS:
            column_type = columns[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise RuntimeError(
                    f"{_TABLE}.{column_name} moet TIMESTAMPTZ zijn; actual={column_type}"
                )
        checks = _checks(bind)
        missing_checks = {_ROLE_CHECK, _STATUS_CHECK, _DELIVERY_CHECK} - checks
        if missing_checks:
            raise RuntimeError(
                f"{_TABLE} mist PostgreSQL CHECK constraints: {sorted(missing_checks)}"
            )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    if not sa.inspect(bind).has_table(_TABLE):
        _create_table(bind)
    else:
        _adopt_existing_table(bind)
    _ensure_indexes(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The household invitation schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
