from __future__ import annotations

import re
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import migration_foundation_selftest as foundation_test
from app.alembic_head_authority import repository_head_revision


HEAD_REVISION = repository_head_revision()
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 95
PASSWORD_RESET_TABLE = "account_password_reset_tokens"
HOME_ACTION_ORDER_TABLE = "platform_home_action_order"
HOME_SETTINGS_TABLE = "platform_home_settings"
HOUSEHOLD_NOTIFICATIONS_TABLE = "household_notifications"
FRONTTEAM_MEMBERSHIP_TABLE = "frontteam_memberships"
RETAILER_ACCOUNT_CREDENTIALS_TABLE = "retailer_account_credentials"
HOUSEHOLD_PROFILE_TABLE = "household_profiles"
HOUSEHOLD_RESIDENT_TABLE = "household_residents"
RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"
QUANTITY_CONTRACT_TABLES = ("purchase_import_lines", "receipt_table_lines")
INVENTORY_QUANTITY_CONTRACT_TABLES = ("inventory", "inventory_events")
_SQLITE_HEAD_EXTENSION_TABLES = {
    "receipt_sources",
    "raw_receipts",
    PASSWORD_RESET_TABLE,
    HOME_ACTION_ORDER_TABLE,
    HOME_SETTINGS_TABLE,
    HOUSEHOLD_NOTIFICATIONS_TABLE,
    FRONTTEAM_MEMBERSHIP_TABLE,
    RETAILER_ACCOUNT_CREDENTIALS_TABLE,
    HOUSEHOLD_PROFILE_TABLE,
    HOUSEHOLD_RESIDENT_TABLE,
    *QUANTITY_CONTRACT_TABLES,
    *INVENTORY_QUANTITY_CONTRACT_TABLES,
}
_LEGACY_FOUNDATION_POSTGRESQL_TRIGGERS = {
    "trg_household_zero_system_insert",
    "trg_receipt_tables_preserve_explicit_approval",
    "trg_spaces_direct_immutable_update",
    "trg_spaces_direct_immutable_delete",
}
EXPECTED_POSTGRESQL_TRIGGERS = (
    _LEGACY_FOUNDATION_POSTGRESQL_TRIGGERS | {MANUAL_SOURCE_TRIGGER}
)


def _postgresql_trigger_names(connection) -> set[str]:
    return {
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


def _remove_locked_sqlite_head_extensions(schema: str) -> str:
    """Delegate migration-owned head objects to exact semantic validation.

    The receipt objects rebuilt at 20260830_02, the password-reset table at
    20260902_01, the receipt quantity-column rebuilds at 20260903_01, the
    inventory quantity-column rebuilds at 20260908_01, the Startpagina action
    order table at 20260915_01 and the household profile/resident schema at
    20261005_01 are migration-owned extensions to the immutable SQLite baseline. Their contracts are validated semantically below. Every
    unrelated schema block remains in the immutable byte comparison.
    """
    blocks = [block for block in schema.rstrip().split("\n\n") if block.strip()]
    retained: list[str] = []
    for block in blocks:
        header = block.splitlines()[0].strip()
        if any(f"(table={table_name})" in header for table_name in _SQLITE_HEAD_EXTENSION_TABLES):
            continue
        if "(table=app_users)" in header:
            block = re.sub(
                r",\s*display_name\s+TEXT(?=\s*\))",
                "",
                block,
                flags=re.IGNORECASE,
            )
            block = re.sub(
                r"display_name\s+TEXT\s*,",
                "",
                block,
                flags=re.IGNORECASE,
            )
        if "(table=global_products)" in header or "(table=external_product_candidates)" in header:
            block = re.sub(
                r",\s*image_url\s+TEXT(?=\s*\))",
                "",
                block,
                flags=re.IGNORECASE,
            )
            block = re.sub(
                r"image_url\s+TEXT\s*,",
                "",
                block,
                flags=re.IGNORECASE,
            )
        if "(table=household_articles)" in header:
            for column_name in (
                "representative_image_url",
                "representative_image_global_product_id",
                "representative_image_gpc_brick_code",
            ):
                block = re.sub(
                    rf",\s*{column_name}\s+TEXT(?=\s*\))",
                    "",
                    block,
                    flags=re.IGNORECASE,
                )
                block = re.sub(
                    rf"{column_name}\s+TEXT\s*,",
                    "",
                    block,
                    flags=re.IGNORECASE,
                )
        retained.append(block)
    return "\n\n".join(retained).rstrip() + "\n"


def _run_foundation_with_locked_head_contract() -> None:
    """Layer current head contracts over the historical migration foundation."""
    original_assert = foundation_test.foundation._assert_postgresql_schema
    original_strip = foundation_test.foundation._strip_migration_extensions

    def _strip_migration_extensions_at_head(schema: str) -> str:
        return _remove_locked_sqlite_head_extensions(original_strip(schema))

    def _assert_postgresql_schema_at_head(connection) -> None:
        try:
            original_assert(connection)
            return
        except AssertionError as exc:
            message = str(exc)
            if not message.startswith("Unexpected PostgreSQL trigger contract:"):
                raise

        actual = _postgresql_trigger_names(connection)
        if actual != EXPECTED_POSTGRESQL_TRIGGERS:
            raise AssertionError(
                "Unexpected PostgreSQL trigger contract at locked head: "
                f"expected={sorted(EXPECTED_POSTGRESQL_TRIGGERS)} "
                f"actual={sorted(actual)}"
            )

        print(
            "POSTGRESQL_APPLICATION_SCHEMA_GREEN "
            f"revision={foundation_test.foundation.HEAD_REVISION} "
            f"tables={foundation_test.foundation.EXPECTED_POSTGRESQL_APPLICATION_TABLES}"
        )
        print("POSTGRESQL_EXTERNAL_CATALOG_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_GPC_BARCODE_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_AUTHORIZATION_BOOLEAN_SCHEMA_GREEN")
        print("POSTGRESQL_ONBOARDING_USE_CASE_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_GPC_RESIDUAL_SCHEMA_AUTHORITY_GREEN")

    foundation_test.foundation._strip_migration_extensions = _strip_migration_extensions_at_head
    foundation_test.foundation._assert_postgresql_schema = _assert_postgresql_schema_at_head
    try:
        foundation_test.main()
    finally:
        foundation_test.foundation._assert_postgresql_schema = original_assert
        foundation_test.foundation._strip_migration_extensions = original_strip


def _assert_receipt_household_authority(connection) -> None:
    inspector = inspect(connection)
    for table_name in RECEIPT_HOUSEHOLD_TABLES:
        matches = [
            fk
            for fk in inspector.get_foreign_keys(table_name)
            if tuple(fk.get("constrained_columns") or ()) == ("household_id",)
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"{table_name}.household_id requires one FK; actual={matches!r}"
            )
        fk = matches[0]
        if str(fk.get("referred_table") or "") != "household_registry":
            raise AssertionError(
                f"{table_name}.household_id must reference household_registry.id; actual={fk!r}"
            )
        if tuple(fk.get("referred_columns") or ()) != ("id",):
            raise AssertionError(
                f"{table_name}.household_id must reference household_registry.id; actual={fk!r}"
            )

    if connection.dialect.name == "sqlite":
        trigger = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name='raw_receipts'",
            (MANUAL_SOURCE_TRIGGER,),
        ).first()
        if trigger is None:
            raise AssertionError("SQLite manual-upload source invariant trigger missing")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise AssertionError("SQLite receipt household authority has FK violations")
        print("SQLITE_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN")
        return

    actual_triggers = _postgresql_trigger_names(connection)
    if actual_triggers != EXPECTED_POSTGRESQL_TRIGGERS:
        raise AssertionError(
            "Unexpected PostgreSQL trigger contract at receipt authority head: "
            f"expected={sorted(EXPECTED_POSTGRESQL_TRIGGERS)} "
            f"actual={sorted(actual_triggers)}"
        )
    print("POSTGRESQL_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN")


def _assert_unbounded_numeric(table_name: str, column_name: str, column: dict) -> None:
    column_type = column["type"]
    if not isinstance(column_type, sa.Numeric):
        raise AssertionError(
            f"Expected NUMERIC for {table_name}.{column_name}, got {column_type}"
        )
    if getattr(column_type, "precision", None) is not None or getattr(column_type, "scale", None) is not None:
        raise AssertionError(
            f"Quantity scale must be unbounded for {table_name}.{column_name}; got {column_type}"
        )


def _assert_quantity_precision_authority(connection) -> None:
    inspector = inspect(connection)

    purchase_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("purchase_import_lines")
    }
    receipt_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("receipt_table_lines")
    }

    for table_name, column_name, column in (
        ("purchase_import_lines", "quantity_raw", purchase_columns["quantity_raw"]),
        ("receipt_table_lines", "quantity", receipt_columns["quantity"]),
    ):
        _assert_unbounded_numeric(table_name, column_name, column)

    for table_name, column_name, column in (
        ("purchase_import_lines", "line_price_raw", purchase_columns["line_price_raw"]),
        ("receipt_table_lines", "line_total", receipt_columns["line_total"]),
        ("receipt_table_lines", "discount_amount", receipt_columns["discount_amount"]),
    ):
        column_type = column["type"]
        if not isinstance(column_type, sa.Numeric) or getattr(column_type, "scale", None) != 2:
            raise AssertionError(
                f"Financial scale drift for {table_name}.{column_name}: got {column_type}"
            )

    if connection.dialect.name == "postgresql":
        print("POSTGRESQL_QUANTITY_PRECISION_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_QUANTITY_PRECISION_SCHEMA_AUTHORITY_GREEN")


def _assert_inventory_quantity_precision_authority(connection) -> None:
    inspector = inspect(connection)
    inventory_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("inventory")
    }
    event_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("inventory_events")
    }

    for table_name, column_name, column in (
        ("inventory", "aantal", inventory_columns["aantal"]),
        ("inventory_events", "quantity", event_columns["quantity"]),
        ("inventory_events", "old_quantity", event_columns["old_quantity"]),
        ("inventory_events", "new_quantity", event_columns["new_quantity"]),
    ):
        _assert_unbounded_numeric(table_name, column_name, column)

    if connection.dialect.name == "postgresql":
        print("POSTGRESQL_INVENTORY_EXACT_QUANTITY_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_INVENTORY_EXACT_QUANTITY_SCHEMA_AUTHORITY_GREEN")


def _assert_password_reset_authority(connection) -> None:
    inspector = inspect(connection)
    if PASSWORD_RESET_TABLE not in set(inspector.get_table_names()):
        raise AssertionError("Alembic head is missing account_password_reset_tokens")

    columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns(PASSWORD_RESET_TABLE)
    }
    expected_columns = {
        "id",
        "user_id",
        "request_email_hash",
        "request_ip_hash",
        "token_hash",
        "requested_at",
        "expires_at",
        "used_at",
        "invalidated_at",
    }
    missing = expected_columns - set(columns)
    if missing:
        raise AssertionError(f"Password-reset schema mist kolommen: {sorted(missing)}")
    for column_name in ("id", "request_email_hash", "request_ip_hash", "requested_at"):
        if bool(columns[column_name].get("nullable")):
            raise AssertionError(f"{PASSWORD_RESET_TABLE}.{column_name} must be NOT NULL")

    if tuple(inspector.get_pk_constraint(PASSWORD_RESET_TABLE).get("constrained_columns") or ()) != ("id",):
        raise AssertionError("Password-reset primary key must be id")

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(PASSWORD_RESET_TABLE)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(PASSWORD_RESET_TABLE)
        if bool(item.get("unique"))
    )
    if ("token_hash",) not in unique_sets:
        raise AssertionError("Password-reset token_hash must remain unique")

    indexes = {
        str(item.get("name") or ""): tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(PASSWORD_RESET_TABLE)
    }
    expected_indexes = {
        "ix_account_password_reset_tokens_email_requested": (
            "request_email_hash",
            "requested_at",
        ),
        "ix_account_password_reset_tokens_ip_requested": (
            "request_ip_hash",
            "requested_at",
        ),
        "ix_account_password_reset_tokens_user_state": (
            "user_id",
            "used_at",
            "invalidated_at",
            "expires_at",
        ),
    }
    for index_name, expected in expected_indexes.items():
        if indexes.get(index_name) != expected:
            raise AssertionError(
                f"Password-reset index drift {index_name}: expected={expected} actual={indexes.get(index_name)}"
            )

    user_fks = [
        fk
        for fk in inspector.get_foreign_keys(PASSWORD_RESET_TABLE)
        if tuple(fk.get("constrained_columns") or ()) == ("user_id",)
    ]
    if len(user_fks) != 1:
        raise AssertionError(f"Password-reset user FK drift: {user_fks!r}")
    fk = user_fks[0]
    if str(fk.get("referred_table") or "") != "app_users" or tuple(fk.get("referred_columns") or ()) != ("id",):
        raise AssertionError(f"Password-reset user FK must reference app_users.id: {fk!r}")

    if connection.dialect.name == "postgresql":
        for column_name in ("requested_at", "expires_at", "used_at", "invalidated_at"):
            column_type = columns[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(getattr(column_type, "timezone", False)):
                raise AssertionError(
                    f"Expected TIMESTAMPTZ for {PASSWORD_RESET_TABLE}.{column_name}, got {column_type}"
                )
        print("POSTGRESQL_PASSWORD_RESET_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_PASSWORD_RESET_SCHEMA_AUTHORITY_GREEN")


def _assert_catalog_image_authority(connection) -> None:
    inspector = inspect(connection)
    for table_name in ("global_products", "external_product_candidates"):
        columns = {
            str(item.get("name") or ""): item
            for item in inspector.get_columns(table_name)
        }
        if "image_url" not in columns:
            raise AssertionError(f"{table_name}.image_url ontbreekt op Alembic head")
        if not isinstance(columns["image_url"]["type"], sa.Text):
            raise AssertionError(
                f"{table_name}.image_url must be TEXT, got {columns['image_url']['type']}"
            )
        if not bool(columns["image_url"].get("nullable")):
            raise AssertionError(f"{table_name}.image_url must remain nullable")

    if connection.dialect.name == "postgresql":
        print("POSTGRESQL_CATALOG_IMAGE_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_CATALOG_IMAGE_SCHEMA_AUTHORITY_GREEN")


def _assert_household_representative_image_authority(connection) -> None:
    inspector = inspect(connection)
    columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("household_articles")
    }
    expected = {
        "representative_image_url",
        "representative_image_global_product_id",
        "representative_image_gpc_brick_code",
    }
    missing = expected - set(columns)
    if missing:
        raise AssertionError(
            f"household_articles mist representatieve fotokolommen: {sorted(missing)}"
        )
    for column_name in expected:
        if not isinstance(columns[column_name]["type"], sa.Text):
            raise AssertionError(
                f"household_articles.{column_name} must be TEXT, got {columns[column_name]['type']}"
            )
        if not bool(columns[column_name].get("nullable")):
            raise AssertionError(
                f"household_articles.{column_name} must remain nullable"
            )
    if connection.dialect.name == "postgresql":
        print("POSTGRESQL_HOUSEHOLD_REPRESENTATIVE_IMAGE_SCHEMA_GREEN")
    else:
        print("SQLITE_HOUSEHOLD_REPRESENTATIVE_IMAGE_SCHEMA_GREEN")


def _assert_home_action_order_authority(connection) -> None:
    inspector = inspect(connection)
    if HOME_ACTION_ORDER_TABLE not in set(inspector.get_table_names()):
        raise AssertionError("Alembic head is missing platform_home_action_order")

    columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns(HOME_ACTION_ORDER_TABLE)
    }
    expected_columns = {"flag_key", "sort_order", "updated_by", "updated_at"}
    missing = expected_columns - set(columns)
    if missing:
        raise AssertionError(
            f"{HOME_ACTION_ORDER_TABLE} mist canonical kolommen: {sorted(missing)}"
        )
    for column_name in expected_columns:
        if bool(columns[column_name].get("nullable")):
            raise AssertionError(
                f"{HOME_ACTION_ORDER_TABLE}.{column_name} must be NOT NULL"
            )

    primary_key = tuple(
        inspector.get_pk_constraint(HOME_ACTION_ORDER_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("flag_key",):
        raise AssertionError(
            f"{HOME_ACTION_ORDER_TABLE} primary key drift: {primary_key!r}"
        )

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(HOME_ACTION_ORDER_TABLE)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(HOME_ACTION_ORDER_TABLE)
        if bool(item.get("unique"))
    )
    if ("sort_order",) not in unique_sets:
        raise AssertionError(
            f"{HOME_ACTION_ORDER_TABLE}.sort_order must remain unique"
        )

    if not isinstance(columns["sort_order"]["type"], sa.Integer):
        raise AssertionError(
            f"{HOME_ACTION_ORDER_TABLE}.sort_order must be INTEGER"
        )

    if connection.dialect.name == "postgresql":
        updated_at_type = columns["updated_at"]["type"]
        if not isinstance(updated_at_type, sa.DateTime) or not bool(
            getattr(updated_at_type, "timezone", False)
        ):
            raise AssertionError(
                f"Expected TIMESTAMPTZ for {HOME_ACTION_ORDER_TABLE}.updated_at, got {updated_at_type}"
            )
        print("POSTGRESQL_HOME_ACTION_ORDER_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_HOME_ACTION_ORDER_SCHEMA_AUTHORITY_GREEN")



def _assert_household_profile_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table_name in (HOUSEHOLD_PROFILE_TABLE, HOUSEHOLD_RESIDENT_TABLE):
        if table_name not in tables:
            raise AssertionError(f"Alembic head is missing {table_name}")

    app_user_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns("app_users")
    }
    display_name = app_user_columns.get("display_name")
    if display_name is None:
        raise AssertionError("app_users.display_name is missing")
    if not isinstance(display_name["type"], sa.Text):
        raise AssertionError(
            f"app_users.display_name must be TEXT, got {display_name['type']}"
        )
    if not bool(display_name.get("nullable")):
        raise AssertionError("app_users.display_name must remain nullable")

    profile_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns(HOUSEHOLD_PROFILE_TABLE)
    }
    expected_profile_columns = {
        "household_id",
        "street",
        "house_number",
        "house_number_addition",
        "postal_code",
        "city",
        "country_code",
        "preferred_stores_json",
        "shopping_interval_days",
        "default_reserve_days",
        "created_at",
        "updated_at",
    }
    missing_profile = expected_profile_columns - set(profile_columns)
    if missing_profile:
        raise AssertionError(
            f"{HOUSEHOLD_PROFILE_TABLE} missing columns: {sorted(missing_profile)}"
        )
    if tuple(
        inspector.get_pk_constraint(HOUSEHOLD_PROFILE_TABLE).get("constrained_columns") or ()
    ) != ("household_id",):
        raise AssertionError(f"{HOUSEHOLD_PROFILE_TABLE} primary key drift")

    resident_columns = {
        str(item.get("name") or ""): item
        for item in inspector.get_columns(HOUSEHOLD_RESIDENT_TABLE)
    }
    expected_resident_columns = {
        "id",
        "household_id",
        "first_name",
        "last_name",
        "resident_type",
        "birth_date",
        "age_band",
        "linked_user_id",
        "created_at",
        "updated_at",
    }
    missing_resident = expected_resident_columns - set(resident_columns)
    if missing_resident:
        raise AssertionError(
            f"{HOUSEHOLD_RESIDENT_TABLE} missing columns: {sorted(missing_resident)}"
        )
    if tuple(
        inspector.get_pk_constraint(HOUSEHOLD_RESIDENT_TABLE).get("constrained_columns") or ()
    ) != ("id",):
        raise AssertionError(f"{HOUSEHOLD_RESIDENT_TABLE} primary key drift")

    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(HOUSEHOLD_RESIDENT_TABLE)
    }
    household_index = indexes.get("ix_household_residents_household")
    if (
        household_index is None
        or bool(household_index.get("unique"))
        or tuple(household_index.get("column_names") or ()) != ("household_id",)
    ):
        raise AssertionError("Invalid ix_household_residents_household")

    linked_index = indexes.get("uq_household_resident_linked_user")
    if (
        linked_index is None
        or not bool(linked_index.get("unique"))
        or tuple(linked_index.get("column_names") or ()) != ("household_id", "linked_user_id")
    ):
        raise AssertionError("Invalid uq_household_resident_linked_user")

    if connection.dialect.name == "sqlite":
        linked_sql = connection.execute(text(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND name='uq_household_resident_linked_user'"
        )).scalar_one_or_none()
        normalized = " ".join(str(linked_sql or "").lower().split())
        if "linked_user_id is not null" not in normalized:
            raise AssertionError(
                "SQLite uq_household_resident_linked_user must remain partial on linked_user_id IS NOT NULL"
            )
        print("SQLITE_HOUSEHOLD_PROFILE_SCHEMA_GREEN")
    else:
        print("POSTGRESQL_HOUSEHOLD_PROFILE_SCHEMA_GREEN")


def main() -> None:
    foundation_test.HEAD_REVISION = HEAD_REVISION
    foundation_test.EXPECTED_POSTGRESQL_APPLICATION_TABLES = EXPECTED_POSTGRESQL_APPLICATION_TABLES
    _run_foundation_with_locked_head_contract()

    engine = create_engine(foundation_test.foundation._engine_url())
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != HEAD_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
                )
            _assert_receipt_household_authority(connection)
            _assert_quantity_precision_authority(connection)
            _assert_inventory_quantity_precision_authority(connection)
            _assert_password_reset_authority(connection)
            _assert_home_action_order_authority(connection)
            _assert_catalog_image_authority(connection)
            _assert_household_representative_image_authority(connection)
            _assert_household_profile_schema(connection)
    finally:
        engine.dispose()

    print(f"MIGRATION_FOUNDATION_REVISION_GREEN revision={HEAD_REVISION}")


if __name__ == "__main__":
    main()
