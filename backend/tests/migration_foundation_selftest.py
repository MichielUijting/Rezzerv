from __future__ import annotations

import gzip
import hashlib
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from capture_schema_baseline import dump_schema


SQLITE_BASELINE_REVISION = "20260827_01"
HEAD_REVISION = "20260828_05"
BASELINE_PATH = Path(__file__).resolve().parents[1] / "alembic" / "baseline_sqlite.sql.gz"
BASELINE_SQL_SHA256 = "e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 50
EXPECTED_SERVER_SESSION_COLUMNS = (
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
EXPECTED_TEMPORAL_INVENTORY_COLUMNS = (
    "effective_at",
    "recorded_at",
    "effective_at_precision",
    "event_priority",
    "source_reference",
    "source_line_id",
    "replayed_at",
)
EXPECTED_TEMPORAL_INDEXES = {
    "idx_inventory_events_temporal_order": (
        "household_id",
        "household_article_id",
        "effective_at",
        "event_priority",
        "id",
    ),
    "idx_inventory_events_source_reference": (
        "source",
        "source_reference",
        "source_line_id",
    ),
}
EXPECTED_BOOLEAN_COLUMNS = {
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
EXPECTED_POSTGRESQL_CHECK_CONSTRAINTS = {
    "ck_app_users_account_status",
    "ck_auth_membership_permission_overrides_effect",
    "ck_auth_permissions_scope",
    "ck_auth_roles_scope",
    "ck_auth_support_sessions_access_level",
    "ck_external_article_product_links_identity",
    "ck_external_article_product_links_status",
    "ck_household_registry_context_type",
}


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _baseline_sql() -> str:
    with gzip.open(BASELINE_PATH, "rt", encoding="utf-8") as baseline_file:
        baseline = baseline_file.read()
    digest = _sha256(baseline)
    if digest != BASELINE_SQL_SHA256:
        raise AssertionError(
            f"Immutable baseline asset hash mismatch: expected={BASELINE_SQL_SHA256} actual={digest}"
        )
    return baseline


def _column(inspector, table_name: str, column_name: str) -> dict:
    columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        raise AssertionError(f"Missing column {table_name}.{column_name}")
    return columns[column_name]


def _strip_migration_extensions(schema: str) -> str:
    """Remove only schema blocks that postdate the immutable SQLite baseline."""
    blocks = [block for block in schema.rstrip().split("\n\n") if block.strip()]
    excluded_headers = {
        "-- table: server_sessions (table=server_sessions)",
        "-- table: frontteam_personal_households (table=frontteam_personal_households)",
        "-- table: actor_object_attributions (table=actor_object_attributions)",
        "-- index: idx_actor_object_attributions_household_actor (table=actor_object_attributions)",
        "-- index: idx_server_sessions_user_active (table=server_sessions)",
        "-- table: inventory_events (table=inventory_events)",
        "-- index: idx_inventory_events_temporal_order (table=inventory_events)",
        "-- index: idx_inventory_events_source_reference (table=inventory_events)",
        "-- index: uq_inventory_active_locationless_household_article (table=inventory)",
    }
    retained = [
        block for block in blocks
        if block.splitlines()[0].strip() not in excluded_headers
    ]
    return "\n\n".join(retained).rstrip() + "\n"


def _server_session_unique_sets(connection, inspector) -> set[tuple[str, ...]]:
    if connection.dialect.name != "sqlite":
        return {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("server_sessions")
        }

    unique_sets: set[tuple[str, ...]] = set()
    indexes = connection.exec_driver_sql(
        'PRAGMA index_list("server_sessions")'
    ).mappings()
    for index in indexes:
        if not bool(index.get("unique")):
            continue
        index_name = str(index.get("name") or "").replace('"', '""')
        unique_sets.add(tuple(
            str(column.get("name") or "")
            for column in connection.exec_driver_sql(
                f'PRAGMA index_info("{index_name}")'
            ).mappings()
        ))
    return unique_sets


def _assert_server_session_schema(connection) -> None:
    inspector = inspect(connection)
    if "server_sessions" not in set(inspector.get_table_names()):
        raise AssertionError("Alembic head is missing server_sessions")
    columns = inspector.get_columns("server_sessions")
    column_names = tuple(str(column.get("name") or "") for column in columns)
    if column_names != EXPECTED_SERVER_SESSION_COLUMNS:
        raise AssertionError(
            "Unexpected server_sessions columns: "
            f"expected={EXPECTED_SERVER_SESSION_COLUMNS!r} actual={column_names!r}"
        )
    if not bool(_column(inspector, "server_sessions", "active_household_id")["nullable"]):
        raise AssertionError("server_sessions.active_household_id must be nullable")
    unique_sets = _server_session_unique_sets(connection, inspector)
    if ("session_token_hash",) not in unique_sets:
        raise AssertionError("server_sessions.session_token_hash must remain unique")
    server_indexes = {index["name"]: index for index in inspector.get_indexes("server_sessions")}
    active_index = server_indexes.get("idx_server_sessions_user_active")
    if not active_index or tuple(active_index.get("column_names") or ()) != (
        "user_id",
        "revoked_at",
        "expires_at",
    ):
        raise AssertionError("Invalid idx_server_sessions_user_active contract")


def _assert_temporal_inventory_schema(connection) -> None:
    inspector = inspect(connection)
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("inventory_events")
    }
    missing = set(EXPECTED_TEMPORAL_INVENTORY_COLUMNS) - set(columns)
    if missing:
        raise AssertionError(f"Missing temporal inventory columns: {sorted(missing)}")
    for column_name in ("effective_at_precision", "event_priority"):
        if bool(columns[column_name].get("nullable")):
            raise AssertionError(f"inventory_events.{column_name} must be NOT NULL")

    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes("inventory_events")
    }
    for index_name, expected_columns in EXPECTED_TEMPORAL_INDEXES.items():
        index = indexes.get(index_name)
        actual_columns = tuple((index or {}).get("column_names") or ())
        actual_unique = bool((index or {}).get("unique"))
        if not index or actual_columns != expected_columns or actual_unique:
            raise AssertionError(
                f"Invalid {index_name}: expected_columns={expected_columns!r} "
                f"expected_unique=False actual_columns={actual_columns!r} "
                f"actual_unique={actual_unique}"
            )

    if not bool(_column(inspector, "inventory", "space_id")["nullable"]):
        raise AssertionError("Waar Inhuis requires nullable inventory.space_id")
    if not bool(_column(inspector, "inventory", "sublocation_id")["nullable"]):
        raise AssertionError("Waar Inhuis requires nullable inventory.sublocation_id")

    if connection.dialect.name == "sqlite":
        inventory_indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes("inventory")
        }
        locationless = inventory_indexes.get("uq_inventory_active_locationless_household_article")
        if not locationless or not bool(locationless.get("unique")) or tuple(locationless.get("column_names") or ()) != (
            "household_id", "household_article_id"
        ):
            raise AssertionError("Invalid SQLite locationless inventory partial unique index")
        locationless_sql = connection.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_inventory_active_locationless_household_article'"
        )).scalar_one_or_none()
        normalized_index = " ".join(str(locationless_sql or "").lower().split())
        for fragment in (
            "create unique index",
            "household_article_id is not null",
            "space_id is null",
            "sublocation_id is null",
            "status",
            "'active'",
        ):
            if fragment not in normalized_index:
                raise AssertionError(
                    "Invalid SQLite locationless inventory partial unique index: "
                    f"missing={fragment!r} index={locationless_sql!r}"
                )

    if connection.dialect.name == "postgresql":
        for column_name in ("effective_at", "recorded_at", "replayed_at"):
            column_type = columns[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(getattr(column_type, "timezone", False)):
                raise AssertionError(
                    f"Expected TIMESTAMPTZ for inventory_events.{column_name}, got {column_type}"
                )
        if not isinstance(columns["event_priority"]["type"], sa.Integer):
            raise AssertionError("inventory_events.event_priority must be INTEGER")


def _assert_postgresql_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if len(tables) != EXPECTED_POSTGRESQL_APPLICATION_TABLES:
        raise AssertionError(
            "PR2b PostgreSQL application schema must contain exactly "
            f"{EXPECTED_POSTGRESQL_APPLICATION_TABLES} application tables; actual={len(tables)}"
        )
    _assert_server_session_schema(connection)
    _assert_temporal_inventory_schema(connection)

    for table_name, column_name in sorted(EXPECTED_BOOLEAN_COLUMNS):
        column = _column(inspector, table_name, column_name)
        if not isinstance(column["type"], sa.Boolean):
            raise AssertionError(
                f"Expected BOOLEAN for {table_name}.{column_name}, got {column['type']}"
            )

    for table_name, column_name in (
        ("receipt_tables", "purchase_at"),
        ("receipt_tables", "created_at"),
        ("product_identities", "created_at"),
        ("server_sessions", "issued_at"),
        ("server_sessions", "expires_at"),
        ("server_sessions", "created_at"),
        ("server_sessions", "updated_at"),
    ):
        column_type = _column(inspector, table_name, column_name)["type"]
        if not isinstance(column_type, sa.DateTime) or not bool(getattr(column_type, "timezone", False)):
            raise AssertionError(
                f"Expected TIMESTAMPTZ for {table_name}.{column_name}, got {column_type}"
            )

    locationless_index = connection.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'inventory'
              AND indexname = 'uq_inventory_active_locationless_household_article'
            """
        )
    ).scalar_one_or_none()
    normalized_index = " ".join(str(locationless_index or "").lower().split())
    for fragment in (
        "create unique index",
        "household_article_id is not null",
        "space_id is null",
        "sublocation_id is null",
        "status",
        "'active'",
    ):
        if fragment not in normalized_index:
            raise AssertionError(
                "Invalid locationless inventory partial unique index: "
                f"missing={fragment!r} index={locationless_index!r}"
            )

    constraints = {
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = current_schema()
                  AND c.contype = 'c'
                  AND c.conname IN (
                    'ck_app_users_account_status',
                    'ck_auth_membership_permission_overrides_effect',
                    'ck_auth_permissions_scope',
                    'ck_auth_roles_scope',
                    'ck_auth_support_sessions_access_level',
                    'ck_external_article_product_links_identity',
                    'ck_external_article_product_links_status',
                    'ck_household_registry_context_type'
                  )
                """
            )
        ).all()
    }
    if constraints != EXPECTED_POSTGRESQL_CHECK_CONSTRAINTS:
        raise AssertionError(
            "Missing PostgreSQL CHECK constraints: "
            f"expected={sorted(EXPECTED_POSTGRESQL_CHECK_CONSTRAINTS)} "
            f"actual={sorted(constraints)}"
        )

    triggers = {
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT t.tgname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND NOT t.tgisinternal
                """
            )
        ).all()
    }
    expected_triggers = {
        "trg_household_zero_system_insert",
        "trg_receipt_tables_preserve_explicit_approval",
    }
    if triggers != expected_triggers:
        raise AssertionError(
            f"Unexpected PostgreSQL trigger contract: expected={sorted(expected_triggers)} "
            f"actual={sorted(triggers)}"
        )

    print(
        "POSTGRESQL_APPLICATION_SCHEMA_GREEN "
        f"revision={HEAD_REVISION} tables={len(tables)}"
    )


def main() -> None:
    expected_mode = str(os.getenv("REZZERV_EXPECT_MIGRATION_MODE") or "").strip()
    if expected_mode not in {
        "sqlite-baseline",
        "sqlite-stamped-runtime",
        "postgresql-lineage",
        "postgresql-application-schema",
    }:
        raise RuntimeError(f"Unsupported REZZERV_EXPECT_MIGRATION_MODE: {expected_mode!r}")

    url = _engine_url()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != HEAD_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
                )

            dialect = connection.dialect.name
            if expected_mode.startswith("sqlite"):
                if dialect != "sqlite":
                    raise AssertionError(f"Expected SQLite, got {dialect}")
                if not url.database or url.database == ":memory:":
                    raise AssertionError("SQLite schema-contract validation requires a file database")
                baseline = _baseline_sql()
                actual = dump_schema(Path(url.database))
                expected_baseline = _strip_migration_extensions(baseline)
                actual_baseline = _strip_migration_extensions(actual)
                if actual_baseline != expected_baseline:
                    raise AssertionError(
                        "SQLite immutable baseline portion differs after migration extensions: "
                        f"expected_sha256={_sha256(expected_baseline)} "
                        f"actual_sha256={_sha256(actual_baseline)}"
                    )
                _assert_server_session_schema(connection)
                _assert_temporal_inventory_schema(connection)
                print(
                    "MIGRATION_SQLITE_SCHEMA_CONTRACT_GREEN "
                    f"mode={expected_mode} source_revision={SQLITE_BASELINE_REVISION} "
                    f"head_revision={HEAD_REVISION} baseline_sha256={_sha256(actual_baseline)}"
                )
            else:
                if dialect != "postgresql":
                    raise AssertionError(f"Expected PostgreSQL, got {dialect}")
                _assert_postgresql_schema(connection)
                print("MIGRATION_POSTGRESQL_LINEAGE_GREEN")
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
