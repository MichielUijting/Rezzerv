from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

import migration_foundation_core_selftest as foundation


HEAD_REVISION = "20260830_01"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 87
DAY_ARTICLE_EVENT_TABLE = "day_article_processing_events"
INVITATION_TABLE = "household_invitations"
RECEIPT_MIGRATION_EXTENDED_TABLE = "receipt_tables"
LINE_OVERRIDE_TABLE = "purchase_import_line_inventory_handling_overrides"
WEBHOOK_DELIVERY_TABLE = "receipt_webhook_deliveries"
FEATURE_SUPPORT_TABLES = {
    "platform_feature_flags",
    "support_threads",
    "support_messages",
    "support_recipients",
}
RESIDUAL_RUNTIME_AUTHORITY_TABLES = {
    LINE_OVERRIDE_TABLE,
    WEBHOOK_DELIVERY_TABLE,
}


def _configure_head_contract() -> None:
    foundation.HEAD_REVISION = HEAD_REVISION
    foundation.EXPECTED_POSTGRESQL_APPLICATION_TABLES = EXPECTED_POSTGRESQL_APPLICATION_TABLES
    foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES = set(
        foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES
    ) | {
        DAY_ARTICLE_EVENT_TABLE,
        INVITATION_TABLE,
        RECEIPT_MIGRATION_EXTENDED_TABLE,
    } | FEATURE_SUPPORT_TABLES | RESIDUAL_RUNTIME_AUTHORITY_TABLES
    foundation.EXPECTED_BOOLEAN_COLUMNS = set(foundation.EXPECTED_BOOLEAN_COLUMNS) | {
        ("spaces", "protected"),
        ("sublocations", "protected"),
        ("platform_feature_flags", "enabled"),
        ("support_threads", "reply_allowed"),
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


def _assert_timestamp_type(connection, table_name: str, column_name: str) -> None:
    column = _column_map(inspect(connection), table_name)[column_name]
    if connection.dialect.name == "postgresql":
        column_type = column["type"]
        if not isinstance(column_type, sa.DateTime) or not bool(
            getattr(column_type, "timezone", False)
        ):
            raise AssertionError(
                f"Expected TIMESTAMPTZ for {table_name}.{column_name}, got {column_type}"
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

    checks = " ".join(
        str(check.get("sqltext") or "").lower()
        for check in inspector.get_check_constraints(DAY_ARTICLE_EVENT_TABLE)
    )
    for fragment in ("event_type", "receipt", "direct_consumption"):
        if fragment not in checks:
            raise AssertionError(
                f"day_article_processing_events mist CHECK-fragment {fragment!r}"
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
        _assert_timestamp_type(
            connection,
            "household_articles",
            "inventory_handling_updated_at",
        )
        _assert_timestamp_type(connection, DAY_ARTICLE_EVENT_TABLE, "created_at")
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
    if tuple(
        inspector.get_pk_constraint(INVITATION_TABLE).get("constrained_columns") or ()
    ) != ("id",):
        raise AssertionError("household_invitations primary key must be id")

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(INVITATION_TABLE)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(INVITATION_TABLE)
        if bool(item.get("unique"))
    )
    if ("token_hash",) not in unique_sets:
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
            _assert_timestamp_type(connection, INVITATION_TABLE, column_name)
        print("POSTGRESQL_HOUSEHOLD_INVITATION_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_HOUSEHOLD_INVITATION_SCHEMA_AUTHORITY_GREEN")


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

    _assert_index(
        inspector,
        "support_threads",
        "idx_support_threads_household_updated",
        ("household_id", "updated_at"),
        unique=False,
    )
    _assert_index(
        inspector,
        "support_threads",
        "idx_support_threads_status_updated",
        ("status", "updated_at"),
        unique=False,
    )
    _assert_index(
        inspector,
        "support_messages",
        "idx_support_messages_thread_created",
        ("thread_id", "created_at"),
        unique=False,
    )
    _assert_index(
        inspector,
        "support_recipients",
        "idx_support_recipients_admin",
        ("admin_user_id", "read_at"),
        unique=False,
    )

    if connection.dialect.name == "postgresql":
        enabled = _column_map(inspector, "platform_feature_flags")["enabled"]
        reply_allowed = _column_map(inspector, "support_threads")["reply_allowed"]
        if not isinstance(enabled["type"], sa.Boolean):
            raise AssertionError("platform_feature_flags.enabled must be BOOLEAN")
        if not isinstance(reply_allowed["type"], sa.Boolean):
            raise AssertionError("support_threads.reply_allowed must be BOOLEAN")
        timestamps = {
            "platform_feature_flags": ("updated_at",),
            "support_threads": ("created_at", "updated_at", "closed_at"),
            "support_messages": ("created_at",),
            "support_recipients": ("read_at", "created_at"),
        }
        for table_name, column_names in timestamps.items():
            for column_name in column_names:
                _assert_timestamp_type(connection, table_name, column_name)
        print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_PLATFORM_FEATURE_SUPPORT_SCHEMA_AUTHORITY_GREEN")


def _assert_zero_residual_runtime_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing_tables = RESIDUAL_RUNTIME_AUTHORITY_TABLES - tables
    if missing_tables:
        raise AssertionError(
            f"Zero-residual runtime authority tables ontbreken: {sorted(missing_tables)}"
        )

    contracts = {
        LINE_OVERRIDE_TABLE: {
            "purchase_import_line_id",
            "household_id",
            "inventory_handling",
            "updated_by_user_id",
            "updated_at",
        },
        WEBHOOK_DELIVERY_TABLE: {
            "svix_id",
            "svix_timestamp",
            "payload_sha256",
            "status",
            "created_at",
            "updated_at",
        },
    }
    for table_name, required in contracts.items():
        columns = _column_map(inspector, table_name)
        missing = required - set(columns)
        if missing:
            raise AssertionError(f"{table_name} mist canonical kolommen: {sorted(missing)}")

    if tuple(
        inspector.get_pk_constraint(LINE_OVERRIDE_TABLE).get("constrained_columns") or ()
    ) != ("purchase_import_line_id",):
        raise AssertionError(f"{LINE_OVERRIDE_TABLE} primary key drift")
    if tuple(
        inspector.get_pk_constraint(WEBHOOK_DELIVERY_TABLE).get("constrained_columns") or ()
    ) != ("svix_id",):
        raise AssertionError(f"{WEBHOOK_DELIVERY_TABLE} primary key drift")

    line_columns = _column_map(inspector, LINE_OVERRIDE_TABLE)
    if bool(line_columns["household_id"].get("nullable")):
        raise AssertionError(f"{LINE_OVERRIDE_TABLE}.household_id must be NOT NULL")
    if bool(line_columns["updated_at"].get("nullable")):
        raise AssertionError(f"{LINE_OVERRIDE_TABLE}.updated_at must be NOT NULL")

    delivery_columns = _column_map(inspector, WEBHOOK_DELIVERY_TABLE)
    for column_name in (
        "svix_timestamp",
        "payload_sha256",
        "status",
        "created_at",
        "updated_at",
    ):
        if bool(delivery_columns[column_name].get("nullable")):
            raise AssertionError(
                f"{WEBHOOK_DELIVERY_TABLE}.{column_name} must be NOT NULL"
            )

    if connection.dialect.name == "postgresql":
        _assert_timestamp_type(connection, LINE_OVERRIDE_TABLE, "updated_at")
        _assert_timestamp_type(connection, WEBHOOK_DELIVERY_TABLE, "created_at")
        _assert_timestamp_type(connection, WEBHOOK_DELIVERY_TABLE, "updated_at")
        print("POSTGRESQL_ZERO_RESIDUAL_RUNTIME_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_ZERO_RESIDUAL_RUNTIME_SCHEMA_AUTHORITY_GREEN")


def main() -> None:
    _configure_head_contract()
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
            _assert_zero_residual_runtime_schema(connection)
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_REVISION_20260830_01_GREEN")


if __name__ == "__main__":
    main()
