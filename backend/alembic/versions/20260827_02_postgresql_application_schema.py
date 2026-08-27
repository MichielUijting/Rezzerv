"""Canonical PostgreSQL application schema built from the immutable SQLite contract.

Revision ID: 20260827_02
Revises: 20260827_01
Create Date: 2026-08-27
"""
from __future__ import annotations

import gzip
import hashlib
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_02"
down_revision: Union[str, None] = "20260827_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQLITE_BASELINE_PATH = Path(__file__).resolve().parents[1] / "baseline_sqlite.sql.gz"
_SQLITE_BASELINE_SHA256 = "e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7"
_EXPECTED_SOURCE_TABLE_COUNT = 49
_EXPECTED_EXPLICIT_INDEX_COUNT = 67
_EXPECTED_SQLITE_TRIGGERS = {
    "trg_app_users_account_status_insert",
    "trg_app_users_account_status_update",
    "trg_household_context_type_insert",
    "trg_household_context_type_update",
    "trg_household_zero_system_insert",
    "trg_receipt_tables_preserve_explicit_approval",
}
_EXPECTED_SQLITE_CHECK_TABLES = {
    "auth_membership_permission_overrides",
    "auth_permissions",
    "auth_roles",
    "auth_support_sessions",
    "external_article_product_links",
}

_BOOLEAN_INTEGER_COLUMNS = {
    ("household_permission_policies", "member_allowed"),
    ("product_identities", "is_primary"),
    ("purchase_import_lines", "is_auto_prefilled"),
    ("receipt_sources", "is_active"),
    ("receipt_table_lines", "is_deleted"),
    ("receipt_table_lines", "is_validated"),
    ("receipt_tables", "totals_overridden"),
    ("spaces", "active"),
    ("sublocations", "active"),
}

_POSTGRESQL_CHECK_CONSTRAINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "auth_membership_permission_overrides": (
        (
            "ck_auth_membership_permission_overrides_effect",
            "effect IN ('allow', 'deny')",
        ),
    ),
    "auth_permissions": (
        ("ck_auth_permissions_scope", "scope IN ('household', 'platform')"),
    ),
    "auth_roles": (
        ("ck_auth_roles_scope", "scope IN ('household', 'platform')"),
    ),
    "auth_support_sessions": (
        (
            "ck_auth_support_sessions_access_level",
            "access_level IN ('metadata', 'read', 'mutate', 'emergency')",
        ),
    ),
    "external_article_product_links": (
        (
            "ck_external_article_product_links_status",
            "status IN ('confirmed', 'inactive')",
        ),
        (
            "ck_external_article_product_links_identity",
            "length(trim(receipt_text_normalized)) > 0 "
            "OR length(trim(external_article_code)) > 0",
        ),
    ),
}


class _SourceContract:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_baseline_sql())

    def close(self) -> None:
        self.connection.close()

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params).fetchall())

    def tables(self) -> list[str]:
        return [
            str(row[0])
            for row in self.rows(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    def table_sql(self, table_name: str) -> str:
        row = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return str(row[0] or "") if row else ""

    def columns(self, table_name: str) -> list[sqlite3.Row]:
        return self.rows(f'PRAGMA table_info("{_sqlite_identifier(table_name)}")')

    def foreign_keys(self, table_name: str) -> list[sqlite3.Row]:
        return self.rows(f'PRAGMA foreign_key_list("{_sqlite_identifier(table_name)}")')

    def index_list(self, table_name: str) -> list[sqlite3.Row]:
        return self.rows(f'PRAGMA index_list("{_sqlite_identifier(table_name)}")')

    def index_info(self, index_name: str) -> list[sqlite3.Row]:
        return self.rows(f'PRAGMA index_info("{_sqlite_identifier(index_name)}")')

    def explicit_indexes(self) -> list[sqlite3.Row]:
        return self.rows(
            "SELECT name, tbl_name, sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL ORDER BY name"
        )

    def triggers(self) -> dict[str, str]:
        return {
            str(row[0]): str(row[1] or "")
            for row in self.rows(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND sql IS NOT NULL ORDER BY name"
            )
        }


def _baseline_sql() -> str:
    with gzip.open(_SQLITE_BASELINE_PATH, "rt", encoding="utf-8") as baseline_file:
        baseline = baseline_file.read()
    actual = hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    if actual != _SQLITE_BASELINE_SHA256:
        raise RuntimeError(
            "Immutable SQLite baseline hash mismatch: "
            f"expected={_SQLITE_BASELINE_SHA256} actual={actual}"
        )
    return baseline


def _sqlite_identifier(value: str) -> str:
    return str(value).replace('"', '""')


def _assert_source_contract(source: _SourceContract) -> None:
    tables = source.tables()
    if len(tables) != _EXPECTED_SOURCE_TABLE_COUNT:
        raise RuntimeError(
            "Unexpected immutable source table count: "
            f"expected={_EXPECTED_SOURCE_TABLE_COUNT} actual={len(tables)}"
        )
    indexes = source.explicit_indexes()
    if len(indexes) != _EXPECTED_EXPLICIT_INDEX_COUNT:
        raise RuntimeError(
            "Unexpected immutable source index count: "
            f"expected={_EXPECTED_EXPLICIT_INDEX_COUNT} actual={len(indexes)}"
        )
    triggers = source.triggers()
    if set(triggers) != _EXPECTED_SQLITE_TRIGGERS:
        raise RuntimeError(
            "Unexpected immutable SQLite trigger contract: "
            f"expected={sorted(_EXPECTED_SQLITE_TRIGGERS)} actual={sorted(triggers)}"
        )
    tables_with_check = {
        name
        for name in tables
        if re.search(r"\bCHECK\s*\(", source.table_sql(name), flags=re.IGNORECASE)
    }
    if tables_with_check != _EXPECTED_SQLITE_CHECK_TABLES:
        raise RuntimeError(
            "Unexpected immutable SQLite CHECK contract: "
            f"expected={sorted(_EXPECTED_SQLITE_CHECK_TABLES)} "
            f"actual={sorted(tables_with_check)}"
        )
    if set(_POSTGRESQL_CHECK_CONSTRAINTS) != _EXPECTED_SQLITE_CHECK_TABLES:
        raise RuntimeError(
            "PostgreSQL CHECK port does not cover the immutable SQLite CHECK tables"
        )


def _is_boolean_column(table_name: str, column_name: str, declared_type: str) -> bool:
    normalized = declared_type.strip().upper()
    return (
        normalized.startswith(("BOOLEAN", "BOOL"))
        or (table_name, column_name) in _BOOLEAN_INTEGER_COLUMNS
        or (
            normalized.startswith("INTEGER")
            and column_name.startswith(("is_", "has_", "can_"))
        )
    )


def _target_type(table_name: str, column_name: str, declared_type: str) -> sa.types.TypeEngine[Any]:
    normalized = str(declared_type or "").strip().upper()
    if not normalized:
        raise RuntimeError(f"Untyped SQLite column cannot be ported: {table_name}.{column_name}")
    if _is_boolean_column(table_name, column_name, normalized):
        return sa.Boolean()
    if normalized.startswith(("DATETIME", "TIMESTAMP")) or column_name.endswith("_at"):
        return sa.DateTime(timezone=True)
    if normalized == "DATE" or column_name.endswith("_date"):
        return sa.Date()
    length = re.search(r"\((\d+)\)", normalized)
    if normalized.startswith(("VARCHAR", "CHAR")):
        return sa.String(length=int(length.group(1)) if length else None)
    if normalized.startswith(("TEXT", "CLOB")):
        return sa.Text()
    if normalized.startswith("BIGINT"):
        return sa.BigInteger()
    if normalized.startswith(("INTEGER", "INT")):
        return sa.Integer()
    if normalized.startswith(("NUMERIC", "DECIMAL")):
        numeric = re.search(r"\((\d+)\s*,\s*(\d+)\)", normalized)
        return (
            sa.Numeric(precision=int(numeric.group(1)), scale=int(numeric.group(2)))
            if numeric
            else sa.Numeric()
        )
    if normalized.startswith(("REAL", "FLOAT", "DOUBLE")):
        return sa.Float()
    if normalized.startswith(("BLOB", "BINARY")):
        return sa.LargeBinary()
    if normalized.startswith("JSON"):
        return sa.Text()
    raise RuntimeError(
        f"Unsupported SQLite declared type for PostgreSQL: "
        f"{table_name}.{column_name}={declared_type!r}"
    )


def _server_default(raw_default: Any, target_type: sa.types.TypeEngine[Any]) -> sa.TextClause | None:
    if raw_default is None:
        return None
    value = str(raw_default).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    if not value or value.upper() == "NULL":
        return None
    if isinstance(target_type, sa.Boolean):
        normalized = value.strip("'\"").lower()
        if normalized in {"0", "false"}:
            return sa.text("false")
        if normalized in {"1", "true"}:
            return sa.text("true")
        raise RuntimeError(f"Unsupported Boolean default: {raw_default!r}")
    if isinstance(target_type, sa.DateTime):
        if value.upper() == "CURRENT_TIMESTAMP" or value.lower().startswith("datetime("):
            return sa.text("CURRENT_TIMESTAMP")
    if isinstance(target_type, sa.Date) and value.upper() == "CURRENT_DATE":
        return sa.text("CURRENT_DATE")
    if value.startswith('"') and value.endswith('"'):
        value = "'" + value[1:-1].replace("'", "''") + "'"
    return sa.text(value)


def _unique_constraints(source: _SourceContract, table_name: str) -> list[sa.UniqueConstraint]:
    constraints: list[sa.UniqueConstraint] = []
    seen: set[tuple[str, ...]] = set()
    for index_row in source.index_list(table_name):
        if not bool(index_row[2]) or str(index_row[3] or "") != "u":
            continue
        index_name = str(index_row[1])
        columns = tuple(
            str(row[2])
            for row in sorted(source.index_info(index_name), key=lambda row: int(row[0]))
            if row[2] is not None
        )
        if columns and columns not in seen:
            seen.add(columns)
            constraints.append(sa.UniqueConstraint(*columns))
    return constraints


def _foreign_key_constraints(source: _SourceContract, table_name: str) -> list[sa.ForeignKeyConstraint]:
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in source.foreign_keys(table_name):
        grouped[int(row[0])].append(row)
    constraints: list[sa.ForeignKeyConstraint] = []
    for foreign_key_id in sorted(grouped):
        rows = sorted(grouped[foreign_key_id], key=lambda row: int(row[1]))
        referred_table = str(rows[0][2])
        kwargs: dict[str, Any] = {}
        on_update = str(rows[0][5] or "").upper()
        on_delete = str(rows[0][6] or "").upper()
        if on_update and on_update != "NO ACTION":
            kwargs["onupdate"] = on_update
        if on_delete and on_delete != "NO ACTION":
            kwargs["ondelete"] = on_delete
        constraints.append(
            sa.ForeignKeyConstraint(
                [str(row[3]) for row in rows],
                [f"{referred_table}.{str(row[4])}" for row in rows],
                **kwargs,
            )
        )
    return constraints


def _postgresql_check_constraints(table_name: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(expression, name=constraint_name)
        for constraint_name, expression in _POSTGRESQL_CHECK_CONSTRAINTS.get(table_name, ())
    ]


def _build_metadata(source: _SourceContract) -> sa.MetaData:
    metadata = sa.MetaData()
    for table_name in source.tables():
        column_rows = source.columns(table_name)
        primary_keys = [str(row[1]) for row in column_rows if int(row[5] or 0) > 0]
        single_integer_autoincrement = (
            len(primary_keys) == 1
            and "AUTOINCREMENT" in source.table_sql(table_name).upper()
        )
        columns: list[sa.Column[Any]] = []
        for row in column_rows:
            column_name = str(row[1])
            target_type = _target_type(table_name, column_name, str(row[2] or ""))
            is_primary_key = int(row[5] or 0) > 0
            columns.append(
                sa.Column(
                    column_name,
                    target_type,
                    nullable=False if is_primary_key else not bool(row[3]),
                    primary_key=is_primary_key,
                    autoincrement=single_integer_autoincrement and is_primary_key,
                    server_default=_server_default(row[4], target_type),
                )
            )
        sa.Table(
            table_name,
            metadata,
            *columns,
            *_unique_constraints(source, table_name),
            *_foreign_key_constraints(source, table_name),
            *_postgresql_check_constraints(table_name),
        )
    return metadata


def _translate_partial_predicate(table_name: str, predicate: str) -> str:
    translated = predicate.strip().rstrip(";")
    boolean_columns = {
        column_name
        for candidate_table, column_name in _BOOLEAN_INTEGER_COLUMNS
        if candidate_table == table_name
    }
    for column_name in sorted(boolean_columns, key=len, reverse=True):
        escaped = re.escape(column_name)
        translated = re.sub(
            rf"\bCOALESCE\s*\(\s*{escaped}\s*,\s*0\s*\)",
            f"COALESCE({column_name}, FALSE)",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(
            rf"\bCOALESCE\s*\(\s*{escaped}\s*,\s*1\s*\)",
            f"COALESCE({column_name}, TRUE)",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(
            rf"\b{escaped}\s*=\s*0\b",
            f"{column_name} IS FALSE",
            translated,
            flags=re.IGNORECASE,
        )
        translated = re.sub(
            rf"\b{escaped}\s*=\s*1\b",
            f"{column_name} IS TRUE",
            translated,
            flags=re.IGNORECASE,
        )
    return translated


def _create_explicit_indexes(
    bind: sa.engine.Connection,
    source: _SourceContract,
    metadata: sa.MetaData,
) -> None:
    for row in source.explicit_indexes():
        index_name = str(row[0])
        table_name = str(row[1])
        source_sql = str(row[2] or "")
        if re.search(r"\bCOLLATE\s+NOCASE\b", source_sql, flags=re.IGNORECASE):
            raise RuntimeError(
                f"Index {index_name} requires explicit PostgreSQL collation semantics"
            )
        info = sorted(source.index_info(index_name), key=lambda item: int(item[0]))
        column_names = [str(item[2]) for item in info if item[2] is not None]
        if len(column_names) != len(info) or not column_names:
            raise RuntimeError(
                f"Expression index {index_name} requires an explicit PostgreSQL port"
            )
        unique_match = re.match(
            r"\s*CREATE\s+(UNIQUE\s+)?INDEX\b",
            source_sql,
            flags=re.IGNORECASE,
        )
        if not unique_match:
            raise RuntimeError(f"Unsupported SQLite index SQL: {index_name}")
        kwargs: dict[str, Any] = {}
        where_match = re.search(
            r"\bWHERE\b(?P<predicate>.+)$",
            source_sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if where_match:
            kwargs["postgresql_where"] = sa.text(
                _translate_partial_predicate(table_name, where_match.group("predicate"))
            )
        table = metadata.tables[table_name]
        sa.Index(
            index_name,
            *[table.c[column_name] for column_name in column_names],
            unique=bool(unique_match.group(1)),
            **kwargs,
        ).create(bind=bind, checkfirst=False)


def _create_server_sessions(bind: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    table = sa.Table(
        "server_sessions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("active_household_id", sa.String(64), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    table.create(bind=bind, checkfirst=False)
    sa.Index(
        "idx_server_sessions_user_active",
        table.c.user_id,
        table.c.revoked_at,
        table.c.expires_at,
    ).create(bind=bind, checkfirst=False)


def _install_postgresql_invariants(bind: sa.engine.Connection) -> None:
    bind.exec_driver_sql(
        "ALTER TABLE household_registry "
        "ADD CONSTRAINT ck_household_registry_context_type "
        "CHECK (context_type IN ('regular', 'system'))"
    )
    bind.exec_driver_sql(
        "ALTER TABLE app_users "
        "ADD CONSTRAINT ck_app_users_account_status "
        "CHECK (account_status IN ('active', 'disabled'))"
    )
    bind.exec_driver_sql(
        """
        CREATE OR REPLACE FUNCTION rezzerv_household_zero_system_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.id::text = '0' AND NEW.context_type <> 'system' THEN
                NEW.context_type := 'system';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TRIGGER trg_household_zero_system_insert
        BEFORE INSERT ON household_registry
        FOR EACH ROW
        EXECUTE FUNCTION rezzerv_household_zero_system_insert()
        """
    )
    bind.exec_driver_sql(
        """
        CREATE OR REPLACE FUNCTION rezzerv_preserve_explicit_receipt_approval()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.approved_at IS NOT NULL
               AND NEW.deleted_at IS NULL
               AND (
                    lower(trim(COALESCE(NEW.parse_status, ''))) NOT IN (
                        'approved', 'approved_override'
                    )
                    OR lower(trim(COALESCE(NEW.workflow_state, 'active'))) = 'returned_to_kassa'
               )
               AND lower(trim(COALESCE(NEW.workflow_state, 'active'))) NOT IN (
                    'archived', 'removed_reimport_allowed', 'legacy_deleted'
               )
               AND EXISTS (
                    SELECT 1
                    FROM raw_receipts rr
                    WHERE rr.id = NEW.raw_receipt_id
                      AND rr.deleted_at IS NULL
               )
            THEN
                NEW.parse_status := CASE
                    WHEN COALESCE(NEW.totals_overridden, FALSE)
                    THEN 'approved_override'
                    ELSE 'approved'
                END;
                IF lower(trim(COALESCE(NEW.workflow_state, 'active'))) = 'returned_to_kassa' THEN
                    NEW.workflow_state := 'active';
                END IF;
                NEW.updated_at := CURRENT_TIMESTAMP;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TRIGGER trg_receipt_tables_preserve_explicit_approval
        BEFORE UPDATE OF parse_status, approved_at ON receipt_tables
        FOR EACH ROW
        EXECUTE FUNCTION rezzerv_preserve_explicit_receipt_approval()
        """
    )


def _create_postgresql_schema(bind: sa.engine.Connection) -> None:
    source = _SourceContract()
    try:
        _assert_source_contract(source)
        metadata = _build_metadata(source)
        metadata.create_all(bind=bind, checkfirst=False)
        _create_explicit_indexes(bind, source, metadata)
        _create_server_sessions(bind)
        _install_postgresql_invariants(bind)
    finally:
        source.close()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if bind.dialect.name == "postgresql":
        _create_postgresql_schema(bind)
        return
    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")


def downgrade() -> None:
    raise RuntimeError(
        "The canonical Rezzerv application-schema revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
