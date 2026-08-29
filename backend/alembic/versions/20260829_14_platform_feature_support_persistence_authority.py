"""Move platform feature-flag and support persistence schema authority to Alembic.

Revision ID: 20260829_14
Revises: 20260829_13
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_14"
down_revision: Union[str, None] = "20260829_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FEATURE_TABLE = "platform_feature_flags"
_THREAD_TABLE = "support_threads"
_MESSAGE_TABLE = "support_messages"
_RECIPIENT_TABLE = "support_recipients"

_THREAD_HOUSEHOLD_INDEX = "idx_support_threads_household_updated"
_THREAD_STATUS_INDEX = "idx_support_threads_status_updated"
_MESSAGE_THREAD_INDEX = "idx_support_messages_thread_created"
_RECIPIENT_ADMIN_INDEX = "idx_support_recipients_admin"

_THREAD_STATUS_CHECK = "ck_support_threads_status"
_THREAD_RECIPIENT_CHECK = "ck_support_threads_recipient_type"

_REQUIRED_COLUMNS = {
    _FEATURE_TABLE: {"flag_key", "enabled", "updated_by", "updated_at"},
    _THREAD_TABLE: {
        "id", "thread_number", "household_id", "created_by_user_id",
        "created_by_name", "subject", "origin_screen_name", "origin_route",
        "origin_app_version", "status", "reply_allowed", "recipient_type",
        "created_at", "updated_at", "closed_at",
    },
    _MESSAGE_TABLE: {
        "id", "thread_id", "sender_user_id", "sender_name", "sender_role",
        "message_text", "created_at",
    },
    _RECIPIENT_TABLE: {
        "id", "thread_id", "household_id", "admin_user_id", "read_at", "created_at",
    },
}
_TIMESTAMP_COLUMNS = {
    _FEATURE_TABLE: {"updated_at": False},
    _THREAD_TABLE: {"created_at": False, "updated_at": False, "closed_at": True},
    _MESSAGE_TABLE: {"created_at": False},
    _RECIPIENT_TABLE: {"read_at": True, "created_at": False},
}
_EXPECTED_INDEXES = {
    _THREAD_TABLE: {
        _THREAD_HOUSEHOLD_INDEX: ("household_id", "updated_at"),
        _THREAD_STATUS_INDEX: ("status", "updated_at"),
    },
    _MESSAGE_TABLE: {
        _MESSAGE_THREAD_INDEX: ("thread_id", "created_at"),
    },
    _RECIPIENT_TABLE: {
        _RECIPIENT_ADMIN_INDEX: ("admin_user_id", "read_at"),
    },
}


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    return sa.DateTime(timezone=True) if dialect_name == "postgresql" else sa.Text()


def _reply_allowed_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    return sa.Boolean() if dialect_name == "postgresql" else sa.Integer()


def _columns(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _indexes(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(table_name)
    }


def _checks(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {
        str(check.get("name") or "")
        for check in sa.inspect(bind).get_check_constraints(table_name)
        if check.get("name")
    }


def _normalize_postgresql_timestamp(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
    *,
    nullable: bool,
    default_current_timestamp: bool = False,
) -> None:
    column = _columns(bind, table_name)[column_name]
    if isinstance(column["type"], sa.DateTime) and bool(
        getattr(column["type"], "timezone", False)
    ):
        return
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'
    )
    using = (
        f"CASE WHEN NULLIF(trim(\"{column_name}\"::text), '') IS NULL "
        f"THEN NULL ELSE \"{column_name}\"::text::timestamptz END"
        if nullable
        else f'"{column_name}"::text::timestamptz'
    )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
        f"TYPE TIMESTAMPTZ USING {using}"
    )
    if default_current_timestamp:
        bind.exec_driver_sql(
            f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
            "SET DEFAULT CURRENT_TIMESTAMP"
        )


def _normalize_postgresql_boolean(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
    *,
    default_sql: str | None,
) -> None:
    column = _columns(bind, table_name)[column_name]
    if isinstance(column["type"], sa.Boolean):
        return
    invalid = bind.execute(
        sa.text(
            f'SELECT DISTINCT "{column_name}"::text FROM "{table_name}" '
            f'WHERE "{column_name}" IS NULL OR lower(trim("{column_name}"::text)) '
            "NOT IN ('0', '1', 'false', 'true', 'f', 't', 'no', 'yes', 'off', 'on')"
        )
    ).all()
    if invalid:
        raise RuntimeError(
            f"{table_name}.{column_name} bevat niet-Boolean legacywaarden: "
            f"{[row[0] for row in invalid]!r}"
        )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'
    )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE BOOLEAN USING '
        f"CASE WHEN lower(trim(\"{column_name}\"::text)) IN "
        "('1', 'true', 't', 'yes', 'on') THEN TRUE ELSE FALSE END"
    )
    if default_sql is not None:
        bind.exec_driver_sql(
            f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
            f"SET DEFAULT {default_sql}"
        )


def _create_feature_table(bind: sa.engine.Connection) -> None:
    op.create_table(
        _FEATURE_TABLE,
        sa.Column("flag_key", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            _timestamp_type(bind.dialect.name),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("flag_key"),
    )


def _create_support_tables(bind: sa.engine.Connection) -> None:
    timestamp = _timestamp_type(bind.dialect.name)
    op.create_table(
        _THREAD_TABLE,
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("thread_number", sa.Text(), nullable=False),
        sa.Column("household_id", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("origin_screen_name", sa.Text(), nullable=False),
        sa.Column("origin_route", sa.Text(), nullable=True),
        sa.Column("origin_app_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'Open'")),
        sa.Column(
            "reply_allowed",
            _reply_allowed_type(bind.dialect.name),
            nullable=False,
            server_default=sa.text("true" if bind.dialect.name == "postgresql" else "1"),
        ),
        sa.Column("recipient_type", sa.Text(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.Column("closed_at", timestamp, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_number", name="uq_support_threads_thread_number"),
        sa.CheckConstraint(
            "status IN ('Open', 'In behandeling', 'Gesloten')",
            name=_THREAD_STATUS_CHECK,
        ),
        sa.CheckConstraint(
            "recipient_type IN ('superuser', 'single_household_admin', 'all_household_admins')",
            name=_THREAD_RECIPIENT_CHECK,
        ),
    )
    op.create_table(
        _MESSAGE_TABLE,
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("sender_user_id", sa.Text(), nullable=False),
        sa.Column("sender_name", sa.Text(), nullable=False),
        sa.Column("sender_role", sa.Text(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["support_threads.id"], ondelete="CASCADE"),
    )
    op.create_table(
        _RECIPIENT_TABLE,
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("admin_user_id", sa.Text(), nullable=False),
        sa.Column("read_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id", "household_id", "admin_user_id",
            name="uq_support_recipients_thread_household_admin",
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["support_threads.id"], ondelete="CASCADE"),
    )


def _adopt_existing_table(bind: sa.engine.Connection, table_name: str) -> None:
    columns = _columns(bind, table_name)
    missing = _REQUIRED_COLUMNS[table_name] - set(columns)
    if missing:
        raise RuntimeError(
            f"Bestaande {table_name} wijkt af van het canonical contract: "
            f"ontbrekend={sorted(missing)}"
        )

    if bind.dialect.name != "postgresql":
        return

    if table_name == _FEATURE_TABLE:
        _normalize_postgresql_boolean(bind, table_name, "enabled", default_sql=None)
        _normalize_postgresql_timestamp(
            bind,
            table_name,
            "updated_at",
            nullable=False,
            default_current_timestamp=True,
        )
    elif table_name == _THREAD_TABLE:
        _normalize_postgresql_boolean(bind, table_name, "reply_allowed", default_sql="TRUE")
        for column_name, nullable in _TIMESTAMP_COLUMNS[table_name].items():
            _normalize_postgresql_timestamp(
                bind, table_name, column_name, nullable=nullable
            )
        checks = _checks(bind, table_name)
        if _THREAD_STATUS_CHECK not in checks:
            op.create_check_constraint(
                _THREAD_STATUS_CHECK,
                table_name,
                "status IN ('Open', 'In behandeling', 'Gesloten')",
            )
        checks = _checks(bind, table_name)
        if _THREAD_RECIPIENT_CHECK not in checks:
            op.create_check_constraint(
                _THREAD_RECIPIENT_CHECK,
                table_name,
                "recipient_type IN ('superuser', 'single_household_admin', 'all_household_admins')",
            )
    else:
        for column_name, nullable in _TIMESTAMP_COLUMNS[table_name].items():
            _normalize_postgresql_timestamp(
                bind, table_name, column_name, nullable=nullable
            )


def _ensure_indexes(bind: sa.engine.Connection) -> None:
    for table_name, expected in _EXPECTED_INDEXES.items():
        indexes = _indexes(bind, table_name)
        for index_name, columns in expected.items():
            if index_name not in indexes:
                op.create_index(index_name, table_name, list(columns), unique=False)
                indexes = _indexes(bind, table_name)


def _validate_primary_key(inspector, table_name: str, expected: tuple[str, ...]) -> None:
    actual = tuple(
        inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    if actual != expected:
        raise RuntimeError(
            f"{table_name} heeft onjuiste primary key: expected={expected!r} actual={actual!r}"
        )


def _has_unique(inspector, table_name: str, expected: tuple[str, ...]) -> bool:
    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table_name)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(table_name)
        if bool(item.get("unique"))
    )
    return expected in unique_sets


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name, required in _REQUIRED_COLUMNS.items():
        if table_name not in tables:
            raise RuntimeError(f"Canonical persistence table ontbreekt: {table_name}")
        columns = _columns(bind, table_name)
        missing = required - set(columns)
        if missing:
            raise RuntimeError(f"{table_name} mist canonical kolommen: {sorted(missing)}")
        _validate_primary_key(inspector, table_name, ("flag_key",) if table_name == _FEATURE_TABLE else ("id",))

    if not _has_unique(inspector, _THREAD_TABLE, ("thread_number",)):
        raise RuntimeError("support_threads.thread_number moet uniek zijn")
    if not _has_unique(
        inspector,
        _RECIPIENT_TABLE,
        ("thread_id", "household_id", "admin_user_id"),
    ):
        raise RuntimeError("support_recipients mist canonical recipient uniqueness")

    for table_name, expected_indexes in _EXPECTED_INDEXES.items():
        indexes = _indexes(bind, table_name)
        for index_name, expected_columns in expected_indexes.items():
            index = indexes.get(index_name)
            actual_columns = tuple((index or {}).get("column_names") or ())
            if index is None or bool(index.get("unique")) or actual_columns != expected_columns:
                raise RuntimeError(
                    f"Invalid {index_name}: expected={expected_columns!r} actual={actual_columns!r}"
                )

    if bind.dialect.name == "postgresql":
        feature_enabled = _columns(bind, _FEATURE_TABLE)["enabled"]["type"]
        if not isinstance(feature_enabled, sa.Boolean):
            raise RuntimeError(
                f"{_FEATURE_TABLE}.enabled moet BOOLEAN zijn; actual={feature_enabled}"
            )
        reply_allowed = _columns(bind, _THREAD_TABLE)["reply_allowed"]["type"]
        if not isinstance(reply_allowed, sa.Boolean):
            raise RuntimeError(
                f"{_THREAD_TABLE}.reply_allowed moet BOOLEAN zijn; actual={reply_allowed}"
            )
        for table_name, timestamp_columns in _TIMESTAMP_COLUMNS.items():
            columns = _columns(bind, table_name)
            for column_name in timestamp_columns:
                column_type = columns[column_name]["type"]
                if not isinstance(column_type, sa.DateTime) or not bool(
                    getattr(column_type, "timezone", False)
                ):
                    raise RuntimeError(
                        f"{table_name}.{column_name} moet TIMESTAMPTZ zijn; actual={column_type}"
                    )
        checks = _checks(bind, _THREAD_TABLE)
        missing_checks = {_THREAD_STATUS_CHECK, _THREAD_RECIPIENT_CHECK} - checks
        if missing_checks:
            raise RuntimeError(
                f"support_threads mist PostgreSQL CHECK constraints: {sorted(missing_checks)}"
            )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table(_FEATURE_TABLE):
        _create_feature_table(bind)
    else:
        _adopt_existing_table(bind, _FEATURE_TABLE)

    inspector = sa.inspect(bind)
    support_presence = {
        table_name: inspector.has_table(table_name)
        for table_name in (_THREAD_TABLE, _MESSAGE_TABLE, _RECIPIENT_TABLE)
    }
    if any(support_presence.values()) and not all(support_presence.values()):
        raise RuntimeError(
            "Incomplete legacy support persistence foundation: "
            f"{support_presence!r}"
        )
    if not any(support_presence.values()):
        _create_support_tables(bind)
    else:
        for table_name in (_THREAD_TABLE, _MESSAGE_TABLE, _RECIPIENT_TABLE):
            _adopt_existing_table(bind, table_name)

    _ensure_indexes(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The platform feature/support persistence schema-authority revision is "
        "intentionally non-destructive and cannot be downgraded."
    )
