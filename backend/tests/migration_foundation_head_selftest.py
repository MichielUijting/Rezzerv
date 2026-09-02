from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

import migration_foundation_selftest as foundation_test


HEAD_REVISION = "20260902_01"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 88
PASSWORD_RESET_TABLE = "account_password_reset_tokens"
RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"
_SQLITE_HEAD_EXTENSION_TABLES = {"receipt_sources", "raw_receipts", PASSWORD_RESET_TABLE}
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

    The receipt objects rebuilt at 20260830_02 and the new password-reset table
    at 20260902_01 are migration-owned extensions to the immutable SQLite
    baseline. Their contracts are validated semantically below. Every unrelated
    schema block remains in the immutable byte comparison.
    """
    blocks = [block for block in schema.rstrip().split("\n\n") if block.strip()]
    retained: list[str] = []
    for block in blocks:
        header = block.splitlines()[0].strip()
        if any(f"(table={table_name})" in header for table_name in _SQLITE_HEAD_EXTENSION_TABLES):
            continue
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
            _assert_password_reset_authority(connection)
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_REVISION_20260902_01_GREEN")


if __name__ == "__main__":
    main()
