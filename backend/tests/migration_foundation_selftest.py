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
HEAD_REVISION = "20260829_10"
BASELINE_PATH = Path(__file__).resolve().parents[1] / "alembic" / "baseline_sqlite.sql.gz"
BASELINE_SQL_SHA256 = "e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 76
PR2G_SCHEMA_AUTHORITY_TABLES = {
    "product_taxonomy",
    "product_taxonomy_synonyms",
    "retailer_receipt_terms",
    "product_taxonomy_terms",
    "product_inventory_groups",
    "product_group_memberships",
    "product_unit_conversions",
    "inventory_item_group_assignments",
    "article_groups",
    "household_articles",
    "household_onboarding",
    "household_product_configuration",
    "spaces",
    "sublocations",
    "shopping_lists",
    "shopping_list_items",
    "loyalty_stamp_transactions",
}
PR2H_SCHEMA_AUTHORITY_TABLES = {
    "external_product_candidates",
    "external_product_index",
    "external_relation_batch_decisions",
}
PR2I_GPC_SCHEMA_AUTHORITY_TABLES = {
    "gpc_segments",
    "gpc_families",
    "gpc_classes",
    "gpc_bricks",
    "gpc_attribute_types",
    "gpc_attribute_values",
    "gpc_brick_attribute_types",
    "gpc_attribute_type_values",
    "gpc_import_runs",
    "gpc_product_groups",
}
PR2K_SCHEMA_AUTHORITY_TABLES = {
    "household_product_use_cases",
}
EXPECTED_HOUSEHOLD_PRODUCT_USE_CASE_COLUMNS = (
    "household_id",
    "use_case",
    "activated_at",
)
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
EXPECTED_EXTERNAL_CATALOG_INDEXES = {
    "external_product_candidates": {
        "idx_external_product_candidates_context": (
            "context_key",
            "retailer_code",
            "candidate_source_name",
            "candidate_source_product_code",
            "variant",
        ),
    },
    "external_product_index": {
        "idx_external_product_index_gtin": ("gtin",),
        "idx_external_product_index_source": ("source_name",),
        "idx_external_product_index_search": ("normalized_search_text",),
    },
    "external_relation_batch_decisions": {
        "idx_external_relation_batch_decisions_candidate": (
            "candidate_id",
            "household_article_id",
            "decision",
        ),
    },
}
EXPECTED_GPC_INDEXES = {
    "gpc_families": {
        "idx_gpc_families_segment": ("segment_code",),
    },
    "gpc_classes": {
        "idx_gpc_classes_family": ("family_code",),
    },
    "gpc_bricks": {
        "idx_gpc_bricks_class": ("class_code",),
    },
}
EXPECTED_GPC_PRODUCT_GROUP_COLUMNS = {
    "gpc_brick_code",
    "gpc_brick_name",
    "gpc_class_code",
    "gpc_class_name",
    "gpc_family_code",
    "gpc_family_name",
    "gpc_segment_code",
    "gpc_segment_name",
    "language_code",
    "source_version",
    "active",
    "created_at",
    "updated_at",
    "gpc_brick_name_en",
    "gpc_class_name_en",
    "gpc_family_name_en",
    "gpc_segment_name_en",
    "brick_definition_includes_en",
    "brick_definition_excludes_en",
    "source",
}
EXPECTED_PRODUCT_INVENTORY_GPC_COLUMNS = {
    "gpc_family_code",
    "gpc_family_name",
    "gpc_class_code",
    "gpc_class_name",
    "gpc_brick_code",
}
EXPECTED_BOOLEAN_COLUMNS = {
    ("auth_membership_roles", "active"),
    ("auth_permissions", "active"),
    ("auth_platform_user_roles", "active"),
    ("auth_roles", "active"),
    ("auth_roles", "system_role"),
    ("external_product_candidates", "is_probable"),
    ("external_product_candidates", "is_user_confirmed"),
    ("external_product_candidates", "is_external_database_override"),
    ("gpc_product_groups", "active"),
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
    "ck_household_product_use_cases_use_case",
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
    """Compare only the immutable-baseline portion not owned by later revisions."""
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
        "-- trigger: trg_app_users_account_status_insert (table=app_users)",
        "-- trigger: trg_app_users_account_status_update (table=app_users)",
    }
    migration_owned_tables = (
        PR2G_SCHEMA_AUTHORITY_TABLES
        | PR2H_SCHEMA_AUTHORITY_TABLES
        | PR2I_GPC_SCHEMA_AUTHORITY_TABLES
        | PR2K_SCHEMA_AUTHORITY_TABLES
    )

    def _is_migration_owned(block: str) -> bool:
        header = block.splitlines()[0].strip()
        if header in excluded_headers:
            return True
        return any(
            f"(table={table_name})" in header
            for table_name in migration_owned_tables
        )

    retained = [block for block in blocks if not _is_migration_owned(block)]
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


def _assert_external_catalog_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing_tables = PR2H_SCHEMA_AUTHORITY_TABLES - tables
    if missing_tables:
        raise AssertionError(
            f"PR2h external catalog tables ontbreken: {sorted(missing_tables)}"
        )

    for table_name, expected_indexes in EXPECTED_EXTERNAL_CATALOG_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes(table_name)
        }
        for index_name, expected_columns in expected_indexes.items():
            index = indexes.get(index_name)
            actual_columns = tuple((index or {}).get("column_names") or ())
            if index is None or bool(index.get("unique")) or actual_columns != expected_columns:
                raise AssertionError(
                    f"Invalid {index_name}: expected_columns={expected_columns!r} "
                    f"actual_columns={actual_columns!r} unique={bool((index or {}).get('unique'))}"
                )

    candidate_columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("external_product_candidates")
    }
    for column_name in (
        "candidate_category",
        "candidate_source_url",
        "raw_payload",
        "external_article_code",
        "is_probable",
        "is_user_confirmed",
        "is_external_database_override",
    ):
        if column_name not in candidate_columns:
            raise AssertionError(
                f"PR2h canonical candidate column ontbreekt: {column_name}"
            )

    if connection.dialect.name == "postgresql":
        for column_name in (
            "is_probable",
            "is_user_confirmed",
            "is_external_database_override",
        ):
            if not isinstance(candidate_columns[column_name]["type"], sa.Boolean):
                raise AssertionError(
                    f"Expected BOOLEAN for external_product_candidates.{column_name}, "
                    f"got {candidate_columns[column_name]['type']}"
                )

    seed_count = int(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM external_product_index
                WHERE source_name IN ('product_taxonomy_seed', 'lidl_catalog_enrichment')
                """
            )
        ).scalar_one()
    )
    if seed_count < 1:
        raise AssertionError("PR2h migration-owned external_product_index seed ontbreekt")


def _assert_gpc_catalog_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing_tables = PR2I_GPC_SCHEMA_AUTHORITY_TABLES - tables
    if missing_tables:
        raise AssertionError(
            f"PR2i GPC catalog tables ontbreken: {sorted(missing_tables)}"
        )

    gpc_product_columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("gpc_product_groups")
    }
    missing_product_columns = EXPECTED_GPC_PRODUCT_GROUP_COLUMNS - set(gpc_product_columns)
    if missing_product_columns:
        raise AssertionError(
            "PR2i gpc_product_groups mist canonical kolommen: "
            + ", ".join(sorted(missing_product_columns))
        )

    inventory_group_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("product_inventory_groups")
    }
    missing_inventory_columns = EXPECTED_PRODUCT_INVENTORY_GPC_COLUMNS - inventory_group_columns
    if missing_inventory_columns:
        raise AssertionError(
            "PR2i product_inventory_groups mist GPC-kolommen: "
            + ", ".join(sorted(missing_inventory_columns))
        )

    for table_name, expected_indexes in EXPECTED_GPC_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes(table_name)
        }
        for index_name, expected_columns in expected_indexes.items():
            index = indexes.get(index_name)
            actual_columns = tuple((index or {}).get("column_names") or ())
            if index is None or bool(index.get("unique")) or actual_columns != expected_columns:
                raise AssertionError(
                    f"Invalid {index_name}: expected_columns={expected_columns!r} "
                    f"actual_columns={actual_columns!r} unique={bool((index or {}).get('unique'))}"
                )

    if connection.dialect.name == "postgresql" and not isinstance(
        gpc_product_columns["active"]["type"], sa.Boolean
    ):
        raise AssertionError(
            "Expected BOOLEAN for gpc_product_groups.active, got "
            f"{gpc_product_columns['active']['type']}"
        )


def _assert_household_product_use_case_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing_tables = PR2K_SCHEMA_AUTHORITY_TABLES - tables
    if missing_tables:
        raise AssertionError(
            f"PR2k household use-case tables ontbreken: {sorted(missing_tables)}"
        )
    columns = tuple(
        str(column.get("name") or "")
        for column in inspector.get_columns("household_product_use_cases")
    )
    if columns != EXPECTED_HOUSEHOLD_PRODUCT_USE_CASE_COLUMNS:
        raise AssertionError(
            "Unexpected household_product_use_cases columns: "
            f"expected={EXPECTED_HOUSEHOLD_PRODUCT_USE_CASE_COLUMNS!r} actual={columns!r}"
        )
    primary_key = tuple(
        inspector.get_pk_constraint("household_product_use_cases").get("constrained_columns") or ()
    )
    if primary_key != ("household_id", "use_case"):
        raise AssertionError(
            "Invalid household_product_use_cases primary key: "
            f"actual={primary_key!r}"
        )


def _assert_postgresql_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if len(tables) != EXPECTED_POSTGRESQL_APPLICATION_TABLES:
        raise AssertionError(
            "PR2k PostgreSQL application schema must contain exactly "
            f"{EXPECTED_POSTGRESQL_APPLICATION_TABLES} application tables; actual={len(tables)}"
        )
    _assert_server_session_schema(connection)
    _assert_temporal_inventory_schema(connection)
    _assert_external_catalog_schema(connection)
    _assert_gpc_catalog_schema(connection)
    _assert_household_product_use_case_schema(connection)

    for table_name, column_name in sorted(EXPECTED_BOOLEAN_COLUMNS):
        column = _column(inspector, table_name, column_name)
        if not isinstance(column["type"], sa.Boolean):
            raise AssertionError(
                f"Expected BOOLEAN for {table_name}.{column_name}, got {column['type']}"
            )

    auth_ip_owner_index = connection.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'auth_platform_user_roles'
              AND indexname = 'idx_auth_single_active_ip_owner'
            """
        )
    ).scalar_one_or_none()
    normalized_auth_index = " ".join(str(auth_ip_owner_index or "").lower().split())
    for fragment in (
        "create unique index",
        "role_key",
        "platform.ip_owner",
        "active is true",
    ):
        if fragment not in normalized_auth_index:
            raise AssertionError(
                "Invalid PostgreSQL authorization partial unique index: "
                f"missing={fragment!r} index={auth_ip_owner_index!r}"
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
                    'ck_household_product_use_cases_use_case',
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
        "trg_spaces_direct_immutable_update",
        "trg_spaces_direct_immutable_delete",
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
    print("POSTGRESQL_EXTERNAL_CATALOG_SCHEMA_AUTHORITY_GREEN")
    print("POSTGRESQL_GPC_BARCODE_SCHEMA_AUTHORITY_GREEN")
    print("POSTGRESQL_AUTHORIZATION_BOOLEAN_SCHEMA_GREEN")
    print("POSTGRESQL_ONBOARDING_USE_CASE_SCHEMA_AUTHORITY_GREEN")


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
                _assert_external_catalog_schema(connection)
                _assert_gpc_catalog_schema(connection)
                _assert_household_product_use_case_schema(connection)
                print(
                    "MIGRATION_SQLITE_SCHEMA_CONTRACT_GREEN "
                    f"mode={expected_mode} source_revision={SQLITE_BASELINE_REVISION} "
                    f"head_revision={HEAD_REVISION} baseline_sha256={_sha256(actual_baseline)}"
                )
                print("SQLITE_EXTERNAL_CATALOG_SCHEMA_AUTHORITY_GREEN")
                print("SQLITE_GPC_BARCODE_SCHEMA_AUTHORITY_GREEN")
                print("SQLITE_ONBOARDING_USE_CASE_SCHEMA_AUTHORITY_GREEN")
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
