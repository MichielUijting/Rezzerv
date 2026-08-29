from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

import migration_foundation_core_selftest as foundation

HEAD_REVISION = "20260829_14"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 85
DAY_ARTICLE_EVENT_TABLE = "day_article_processing_events"
INVITATION_TABLE = "household_invitations"
FEATURE_SUPPORT_TABLES = {
    "platform_feature_flags",
    "support_threads",
    "support_messages",
    "support_recipients",
}


def _configure_revision_14_contract() -> None:
    foundation.HEAD_REVISION = HEAD_REVISION
    foundation.EXPECTED_POSTGRESQL_APPLICATION_TABLES = EXPECTED_POSTGRESQL_APPLICATION_TABLES
    foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES = set(
        foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES
    ) | {DAY_ARTICLE_EVENT_TABLE, INVITATION_TABLE} | FEATURE_SUPPORT_TABLES
    foundation.EXPECTED_BOOLEAN_COLUMNS = set(foundation.EXPECTED_BOOLEAN_COLUMNS) | {
        ("spaces", "protected"),
        ("sublocations", "protected"),
        ("platform_feature_flags", "enabled"),
        ("support_threads", "reply_allowed"),
    }
    foundation.EXPECTED_POSTGRESQL_CHECK_CONSTRAINTS = set(
        foundation.EXPECTED_POSTGRESQL_CHECK_CONSTRAINTS
    ) | {
        "ck_support_threads_status",
        "ck_support_threads_recipient_type",
    }


def _column_map(inspector, table_name: str) -> dict[str, dict]:
    return {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }


def _assert_index(
    inspector,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    unique: bool,
) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(table_name)
    }
    index = indexes.get(index_name)
    if (
        index is None
        or bool(index.get("unique")) is not unique
        or tuple(index.get("column_names") or ()) != columns
    ):
        raise AssertionError(
            f"Invalid {index_name}: expected_columns={columns!r} unique={unique} "
            f"actual={index!r}"
        )


def _assert_day_article_direct_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if DAY_ARTICLE_EVENT_TABLE not in tables:
        raise AssertionError("Alembic head is missing day_article_processing_events")

    required_columns = {
        "household_articles": {
            "default_inventory_handling",
            "inventory_handling_updated_at",
            "inventory_handling_updated_by_user_id",
        },
        "spaces": {"system_key", "protected"},
        "sublocations": {"system_key", "protected"},
        DAY_ARTICLE_EVENT_TABLE: {
            "id",
            "household_id",
            "household_article_id",
            "idempotency_key",
            "event_type",
            "quantity",
            "space_id",
            "sublocation_id",
            "actor_user_id",
            "created_at",
        },
    }
    for table_name, required in required_columns.items():
        missing = required - set(_column_map(inspector, table_name))
        if missing:
            raise AssertionError(
                f"{table_name} mist dagartikel/Direct-kolommen: {sorted(missing)}"
            )

    _assert_index(
        inspector,
        "spaces",
        "idx_spaces_household_system_key",
        ("household_id", "system_key"),
        unique=True,
    )
    _assert_index(
        inspector,
        "sublocations",
        "idx_sublocations_space_system_key",
        ("space_id", "system_key"),
        unique=True,
    )
    _assert_index(
        inspector,
        DAY_ARTICLE_EVENT_TABLE,
        "idx_day_article_events_article",
        ("household_id", "household_article_id", "created_at"),
        unique=False,
    )

    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(DAY_ARTICLE_EVENT_TABLE)
    }
    unique_sets.update(
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(DAY_ARTICLE_EVENT_TABLE)
        if bool(index.get("unique"))
    )
    if ("household_id", "idempotency_key", "event_type") not in unique_sets:
        raise AssertionError("day_article_processing_events mist idempotency uniqueness")

    checks = inspector.get_check_constraints(DAY_ARTICLE_EVENT_TABLE)
    normalized_checks = " ".join(
        str(check.get("sqltext") or "").lower()
        for check in checks
    )
    for fragment in ("event_type", "receipt", "direct_consumption"):
        if fragment not in normalized_checks:
            raise AssertionError(
                "day_article_processing_events mist event_type CHECK-contract: "
                f"missing={fragment!r} checks={checks!r}"
            )

    handling = _column_map(inspector, "household_articles")["default_inventory_handling"]
    if bool(handling.get("nullable")):
        raise AssertionError("household_articles.default_inventory_handling must be NOT NULL")

    if connection.dialect.name == "postgresql":
        for table_name in ("spaces", "sublocations"):
            protected = _column_map(inspector, table_name)["protected"]
            if not isinstance(protected["type"], sa.Boolean):
                raise AssertionError(
                    f"Expected BOOLEAN for {table_name}.protected, got {protected['type']}"
                )
            if bool(protected.get("nullable")):
                raise AssertionError(f"{table_name}.protected must be NOT NULL")

        for table_name, column_name in (
            ("household_articles", "inventory_handling_updated_at"),
            (DAY_ARTICLE_EVENT_TABLE, "created_at"),
        ):
            column_type = _column_map(inspector, table_name)[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise AssertionError(
                    f"Expected TIMESTAMPTZ for {table_name}.{column_name}, got {column_type}"
                )
        print("POSTGRESQL_DAY_ARTICLE_DIRECT_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_DAY_ARTICLE_DIRECT_SCHEMA_AUTHORITY_GREEN")


def _assert_household_invitation_schema(connection) -> None:
    inspector = inspect(connection)
    if INVITATION_TABLE not in set(inspector.get_table_names()):
        raise AssertionError("Alembic head is missing household_invitations")

    columns = _column_map(inspector, INVITATION_TABLE)
    required = {
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
    missing = required - set(columns)
    if missing:
        raise AssertionError(f"household_invitations mist canonical kolommen: {sorted(missing)}")

    primary_key = tuple(
        inspector.get_pk_constraint(INVITATION_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("id",):
        raise AssertionError(f"Invalid household_invitations primary key: {primary_key!r}")

    token_unique = any(
        tuple(item.get("column_names") or ()) == ("token_hash",)
        for item in inspector.get_unique_constraints(INVITATION_TABLE)
    )
    token_unique = token_unique or any(
        bool(item.get("unique"))
        and tuple(item.get("column_names") or ()) == ("token_hash",)
        for item in inspector.get_indexes(INVITATION_TABLE)
    )
    if not token_unique:
        raise AssertionError("household_invitations.token_hash must remain unique")

    _assert_index(
        inspector,
        INVITATION_TABLE,
        "idx_household_invitations_one_pending",
        ("household_id", "invitee_email"),
        unique=True,
    )
    _assert_index(
        inspector,
        INVITATION_TABLE,
        "idx_household_invitations_household_status",
        ("household_id", "status", "created_at"),
        unique=False,
    )
    _assert_index(
        inspector,
        INVITATION_TABLE,
        "idx_household_invitations_expiry",
        ("status", "expires_at"),
        unique=False,
    )

    if connection.dialect.name == "postgresql":
        for column_name in (
            "expires_at",
            "created_at",
            "updated_at",
            "accepted_at",
            "revoked_at",
            "last_delivery_attempt_at",
            "last_delivered_at",
        ):
            column_type = columns[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise AssertionError(
                    f"Expected TIMESTAMPTZ for household_invitations.{column_name}, got {column_type}"
                )
        check_names = {
            str(check.get("name") or "")
            for check in inspector.get_check_constraints(INVITATION_TABLE)
        }
        expected_checks = {
            "ck_household_invitations_role_key",
            "ck_household_invitations_status",
            "ck_household_invitations_delivery_status",
        }
        if not expected_checks.issubset(check_names):
            raise AssertionError(
                "household_invitations mist PostgreSQL CHECK constraints: "
                f"{sorted(expected_checks - check_names)}"
            )
        print("POSTGRESQL_HOUSEHOLD_INVITATION_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_HOUSEHOLD_INVITATION_SCHEMA_AUTHORITY_GREEN")


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


def _assert_platform_feature_support_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing_tables = FEATURE_SUPPORT_TABLES - tables
    if missing_tables:
        raise AssertionError(
            f"Platform feature/support persistence tables ontbreken: {sorted(missing_tables)}"
        )

    required_columns = {
        "platform_feature_flags": {"flag_key", "enabled", "updated_by", "updated_at"},
        "support_threads": {
            "id", "thread_number", "household_id", "created_by_user_id",
            "created_by_name", "subject", "origin_screen_name", "origin_route",
            "origin_app_version", "status", "reply_allowed", "recipient_type",
            "created_at", "updated_at", "closed_at",
        },
        "support_messages": {
            "id", "thread_id", "sender_user_id", "sender_name", "sender_role",
            "message_text", "created_at",
        },
        "support_recipients": {
            "id", "thread_id", "household_id", "admin_user_id", "read_at", "created_at",
        },
    }
    for table_name, required in required_columns.items():
        missing = required - set(_column_map(inspector, table_name))
        if missing:
            raise AssertionError(f"{table_name} mist canonical kolommen: {sorted(missing)}")

    if tuple(
        inspector.get_pk_constraint("platform_feature_flags").get("constrained_columns") or ()
    ) != ("flag_key",):
        raise AssertionError("platform_feature_flags primary key must be flag_key")
    for table_name in ("support_threads", "support_messages", "support_recipients"):
        if tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        ) != ("id",):
            raise AssertionError(f"{table_name} primary key must be id")

    if not _has_unique(inspector, "support_threads", ("thread_number",)):
        raise AssertionError("support_threads.thread_number must remain unique")
    if not _has_unique(
        inspector,
        "support_recipients",
        ("thread_id", "household_id", "admin_user_id"),
    ):
        raise AssertionError("support_recipients recipient identity must remain unique")

    for table_name, index_name, columns in (
        ("support_threads", "idx_support_threads_household_updated", ("household_id", "updated_at")),
        ("support_threads", "idx_support_threads_status_updated", ("status", "updated_at")),
        ("support_messages", "idx_support_messages_thread_created", ("thread_id", "created_at")),
        ("support_recipients", "idx_support_recipients_admin", ("admin_user_id", "read_at")),
    ):
        _assert_index(inspector, table_name, index_name, columns, unique=False)

    if connection.dialect.name == "postgresql":
        feature_enabled = _column_map(inspector, "platform_feature_flags")["enabled"]
        if not isinstance(feature_enabled["type"], sa.Boolean):
            raise AssertionError(
                f"Expected BOOLEAN for platform_feature_flags.enabled, got {feature_enabled['type']}"
            )
        reply_allowed = _column_map(inspector, "support_threads")["reply_allowed"]
        if not isinstance(reply_allowed["type"], sa.Boolean):
            raise AssertionError(
                f"Expected BOOLEAN for support_threads.reply_allowed, got {reply_allowed['type']}"
            )
        timestamp_columns = {
            "platform_feature_flags": ("updated_at",),
            "support_threads": ("created_at", "updated_at", "closed_at"),
            "support_messages": ("created_at",),
            "support_recipients": ("read_at", "created_at"),
        }
        for table_name, column_names in timestamp_columns.items():
            columns = _column_map(inspector, table_name)
            for column_name in column_names:
                column_type = columns[column_name]["type"]
                if not isinstance(column_type, sa.DateTime) or not bool(
                    getattr(column_type, "timezone", False)
                ):
                    raise AssertionError(
                        f"Expected TIMESTAMPTZ for {table_name}.{column_name}, got {column_type}"
                    )
        check_names = {
            str(check.get("name") or "")
            for check in inspector.get_check_constraints("support_threads")
        }
        expected_checks = {
            "ck_support_threads_status",
            "ck_support_threads_recipient_type",
        }
        if not expected_checks.issubset(check_names):
            raise AssertionError(
                "support_threads mist PostgreSQL CHECK constraints: "
                f"{sorted(expected_checks - check_names)}"
            )
        print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_PLATFORM_FEATURE_SUPPORT_SCHEMA_AUTHORITY_GREEN")


def main() -> None:
    _configure_revision_14_contract()
    foundation.main()

    engine = create_engine(foundation._engine_url())
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != HEAD_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
                )
            _assert_day_article_direct_schema(connection)
            _assert_household_invitation_schema(connection)
            _assert_platform_feature_support_schema(connection)
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_REVISION_14_GREEN")


if __name__ == "__main__":
    main()
