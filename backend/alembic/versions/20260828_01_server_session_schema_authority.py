"""Move server_sessions schema authority from runtime code to Alembic.

Revision ID: 20260828_01
Revises: 20260827_02
Create Date: 2026-08-28
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_01"
down_revision: Union[str, None] = "20260827_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SERVER_SESSION_COLUMNS = (
    "id",
    "session_token_hash",
    "user_id",
    "active_household_id",
    "issued_at",
    "expires_at",
    "session_version",
    "revoked_at",
    "replaced_by_session_id",
    "created_at",
    "updated_at",
)
_SERVER_SESSION_COLUMN_CONTRACT = (
    ("id", "VARCHAR(64)", False, None, 1),
    ("session_token_hash", "VARCHAR(64)", True, None, 0),
    ("user_id", "VARCHAR(64)", True, None, 0),
    ("active_household_id", "VARCHAR(64)", None, None, 0),
    ("issued_at", "TIMESTAMP", True, None, 0),
    ("expires_at", "TIMESTAMP", True, None, 0),
    ("session_version", "INTEGER", True, "1", 0),
    ("revoked_at", "TIMESTAMP", False, None, 0),
    ("replaced_by_session_id", "VARCHAR(64)", False, None, 0),
    ("created_at", "TIMESTAMP", True, "CURRENT_TIMESTAMP", 0),
    ("updated_at", "TIMESTAMP", True, "CURRENT_TIMESTAMP", 0),
)
_SERVER_SESSION_ACTIVE_INDEX_COLUMNS = (
    "user_id",
    "revoked_at",
    "expires_at",
)
_SERVER_SESSION_TABLE_SQL = """
    CREATE TABLE {table_name} (
        id VARCHAR(64) PRIMARY KEY,
        session_token_hash VARCHAR(64) NOT NULL UNIQUE,
        user_id VARCHAR(64) NOT NULL,
        active_household_id VARCHAR(64) NULL,
        issued_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        session_version INTEGER NOT NULL DEFAULT 1,
        revoked_at TIMESTAMP NULL,
        replaced_by_session_id VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""


def _sqlite_schema_objects(
    bind: sa.engine.Connection,
    object_type: str,
) -> list[Mapping[str, Any]]:
    return list(bind.execute(sa.text("""
        SELECT name, sql
        FROM sqlite_master
        WHERE type = :object_type AND tbl_name = 'server_sessions'
          AND sql IS NOT NULL
        ORDER BY name
    """), {"object_type": object_type}).mappings())


def _sqlite_incoming_server_session_foreign_keys(
    bind: sa.engine.Connection,
) -> list[str]:
    incoming: list[str] = []
    table_names = bind.execute(sa.text("""
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
    """)).scalars()
    for table_name in table_names:
        escaped_name = str(table_name).replace('"', '""')
        foreign_keys = bind.exec_driver_sql(
            f'PRAGMA foreign_key_list("{escaped_name}")'
        ).mappings()
        if any(
            str(item.get("table") or "").lower() == "server_sessions"
            for item in foreign_keys
        ):
            incoming.append(str(table_name))
    return incoming


def _sqlite_pragma_rows(
    bind: sa.engine.Connection,
    pragma_name: str,
    object_name: str,
) -> list[Mapping[str, Any]]:
    escaped_name = str(object_name).replace('"', '""')
    return list(bind.exec_driver_sql(
        f'PRAGMA {pragma_name}("{escaped_name}")'
    ).mappings())


def _validate_sqlite_columns(
    bind: sa.engine.Connection,
    *,
    nullable_household: bool,
) -> None:
    actual_columns = _sqlite_pragma_rows(bind, "table_info", "server_sessions")
    expected_columns = []
    for name, declared_type, not_null, default, primary_key_position in (
        _SERVER_SESSION_COLUMN_CONTRACT
    ):
        expected_not_null = (
            not nullable_household if name == "active_household_id" else not_null
        )
        expected_columns.append((
            name,
            declared_type,
            bool(expected_not_null),
            default,
            primary_key_position,
        ))
    actual_contract = [
        (
            str(column.get("name") or ""),
            str(column.get("type") or "").upper(),
            bool(column.get("notnull")),
            None if column.get("dflt_value") is None else str(column["dflt_value"]),
            int(column.get("pk") or 0),
        )
        for column in actual_columns
    ]
    if actual_contract != expected_columns:
        raise RuntimeError("Onverwacht server_sessions-kolomcontract")


def _validate_sqlite_unique_contract(bind: sa.engine.Connection) -> None:
    indexes = _sqlite_pragma_rows(bind, "index_list", "server_sessions")
    unique_contracts = []
    for index in indexes:
        if not bool(index.get("unique")):
            continue
        index_name = str(index.get("name") or "")
        columns = tuple(
            str(column.get("name") or "")
            for column in _sqlite_pragma_rows(bind, "index_info", index_name)
        )
        unique_contracts.append((str(index.get("origin") or ""), columns))
    if sorted(unique_contracts) != sorted((
        ("pk", ("id",)),
        ("u", ("session_token_hash",)),
    )):
        raise RuntimeError("Onverwacht server_sessions-UNIQUE/PK-contract")


def _validate_sqlite_active_index(bind: sa.engine.Connection) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in _sqlite_pragma_rows(bind, "index_list", "server_sessions")
    }
    index = indexes.get("idx_server_sessions_user_active")
    if not index or bool(index.get("unique")) or bool(index.get("partial")):
        raise RuntimeError("Ongeldige idx_server_sessions_user_active")
    columns = tuple(
        str(column.get("name") or "")
        for column in _sqlite_pragma_rows(
            bind,
            "index_info",
            "idx_server_sessions_user_active",
        )
    )
    if columns != _SERVER_SESSION_ACTIVE_INDEX_COLUMNS:
        raise RuntimeError("Ongeldige idx_server_sessions_user_active-kolommen")


def _validate_sqlite_schema(
    bind: sa.engine.Connection,
    *,
    nullable_household: bool,
) -> None:
    _validate_sqlite_columns(bind, nullable_household=nullable_household)
    _validate_sqlite_unique_contract(bind)
    _validate_sqlite_active_index(bind)


def _create_sqlite_server_sessions(bind: sa.engine.Connection) -> None:
    bind.execute(sa.text(_SERVER_SESSION_TABLE_SQL.format(
        table_name="server_sessions"
    )))
    bind.execute(sa.text("""
        CREATE INDEX idx_server_sessions_user_active
        ON server_sessions(user_id, revoked_at, expires_at)
    """))
    _validate_sqlite_schema(bind, nullable_household=True)


def _upgrade_sqlite_active_household_nullable(
    bind: sa.engine.Connection,
) -> None:
    _validate_sqlite_schema(bind, nullable_household=False)
    if sa.inspect(bind).get_foreign_keys("server_sessions"):
        raise RuntimeError("server_sessions bevat onverwachte foreign keys")
    incoming_foreign_keys = _sqlite_incoming_server_session_foreign_keys(bind)
    if incoming_foreign_keys:
        raise RuntimeError(
            "Onverwachte inkomende server_sessions-foreign keys: "
            + ", ".join(sorted(incoming_foreign_keys))
        )
    if _sqlite_schema_objects(bind, "trigger"):
        raise RuntimeError("server_sessions bevat onverwachte triggers")
    dependent_views = bind.execute(sa.text("""
        SELECT name FROM sqlite_master
        WHERE type = 'view' AND lower(sql) LIKE '%server_sessions%'
    """)).scalars().all()
    if dependent_views:
        raise RuntimeError(
            "Onverwachte server_sessions-views: " + ", ".join(sorted(dependent_views))
        )

    user_indexes = _sqlite_schema_objects(bind, "index")
    expected_index_names = {"idx_server_sessions_user_active"}
    unexpected_indexes = {
        str(item["name"]) for item in user_indexes
    } - expected_index_names
    if unexpected_indexes:
        raise RuntimeError(
            "Onverwachte server_sessions-indexen: "
            + ", ".join(sorted(unexpected_indexes))
        )

    temporary_table = "server_sessions__schema_authority"
    if sa.inspect(bind).has_table(temporary_table):
        raise RuntimeError("Tijdelijke server_sessions-authoritytabel bestaat al")

    column_list = ", ".join(_SERVER_SESSION_COLUMNS)
    bind.execute(sa.text(_SERVER_SESSION_TABLE_SQL.format(table_name=temporary_table)))
    before_count = int(bind.execute(sa.text(
        "SELECT COUNT(*) FROM server_sessions"
    )).scalar_one())
    bind.execute(sa.text(f"""
        INSERT INTO {temporary_table} ({column_list})
        SELECT {column_list} FROM server_sessions
    """))
    copied_count = int(bind.execute(sa.text(
        f"SELECT COUNT(*) FROM {temporary_table}"
    )).scalar_one())
    if copied_count != before_count:
        raise RuntimeError("server_sessions-rowcount wijkt af tijdens schema-upgrade")

    differences = int(bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM (
            SELECT {column_list} FROM server_sessions
            EXCEPT
            SELECT {column_list} FROM {temporary_table}
        )
    """)).scalar_one())
    if differences:
        raise RuntimeError("server_sessions-data wijkt af tijdens schema-upgrade")

    bind.execute(sa.text("DROP TABLE server_sessions"))
    bind.execute(sa.text(
        f"ALTER TABLE {temporary_table} RENAME TO server_sessions"
    ))
    bind.execute(sa.text("""
        CREATE INDEX idx_server_sessions_user_active
        ON server_sessions(user_id, revoked_at, expires_at)
    """))
    _validate_sqlite_schema(bind, nullable_household=True)
    after_count = int(bind.execute(sa.text(
        "SELECT COUNT(*) FROM server_sessions"
    )).scalar_one())
    if after_count != before_count:
        raise RuntimeError("server_sessions-rowcount wijkt af na schema-upgrade")


def _upgrade_sqlite(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("server_sessions"):
        _create_sqlite_server_sessions(bind)
        return

    columns = {
        str(column.get("name") or ""): column
        for column in _sqlite_pragma_rows(bind, "table_info", "server_sessions")
    }
    household_column = columns.get("active_household_id")
    if household_column is None:
        raise RuntimeError("server_sessions mist active_household_id")
    nullable_household = not bool(household_column.get("notnull"))
    if nullable_household:
        _validate_sqlite_schema(bind, nullable_household=True)
        return
    _upgrade_sqlite_active_household_nullable(bind)


def _validate_postgresql(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("server_sessions"):
        raise RuntimeError("PostgreSQL mist canonical server_sessions")

    columns = inspector.get_columns("server_sessions")
    actual_names = tuple(str(column.get("name") or "") for column in columns)
    if actual_names != _SERVER_SESSION_COLUMNS:
        raise RuntimeError(
            "Onverwacht PostgreSQL server_sessions-kolomcontract: "
            f"{actual_names!r}"
        )
    nullable = {
        str(column.get("name") or ""): bool(column.get("nullable"))
        for column in columns
    }
    expected_nullable = {
        "id": False,
        "session_token_hash": False,
        "user_id": False,
        "active_household_id": True,
        "issued_at": False,
        "expires_at": False,
        "session_version": False,
        "revoked_at": True,
        "replaced_by_session_id": True,
        "created_at": False,
        "updated_at": False,
    }
    if nullable != expected_nullable:
        raise RuntimeError(
            "Onverwacht PostgreSQL server_sessions-nullabilitycontract: "
            f"{nullable!r}"
        )

    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("server_sessions")
    }
    if ("session_token_hash",) not in unique_sets:
        raise RuntimeError("PostgreSQL session_token_hash is niet UNIQUE")

    indexes = {
        str(index.get("name") or ""): tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("server_sessions")
    }
    if indexes.get("idx_server_sessions_user_active") != (
        _SERVER_SESSION_ACTIVE_INDEX_COLUMNS
    ):
        raise RuntimeError("Ongeldig PostgreSQL idx_server_sessions_user_active")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _upgrade_sqlite(bind)
        return
    if bind.dialect.name == "postgresql":
        _validate_postgresql(bind)
        return
    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")


def downgrade() -> None:
    raise RuntimeError(
        "The server-session schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
