"""Additive schema preparation for roles/account model v2.

This foundation does not activate platform-only sessions or credential hashing.
Population of password_hash and credential cutover belong to a later 9.1 slice.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_DISABLED = "disabled"
ACCOUNT_STATUSES = frozenset({ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_DISABLED})

HOUSEHOLD_CONTEXT_REGULAR = "regular"
HOUSEHOLD_CONTEXT_SYSTEM = "system"
HOUSEHOLD_CONTEXT_TYPES = frozenset(
    {HOUSEHOLD_CONTEXT_REGULAR, HOUSEHOLD_CONTEXT_SYSTEM}
)


def _column_names(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return set()
    return {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns(table_name)
    }


def ensure_roles_v2_account_and_household_foundation(conn: Connection) -> None:
    household_columns = _column_names(conn, "household_registry")
    if household_columns and "context_type" not in household_columns:
        conn.execute(text(
            "ALTER TABLE household_registry "
            "ADD COLUMN context_type TEXT NOT NULL DEFAULT 'regular'"
        ))
    if household_columns:
        conn.execute(text(
            "UPDATE household_registry "
            "SET context_type = 'regular' "
            "WHERE context_type IS NULL OR trim(context_type) = ''"
        ))
        conn.execute(text(
            "UPDATE household_registry SET context_type = 'system' WHERE id = '0'"
        ))
        if conn.dialect.name == "sqlite":
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_household_context_type_insert
                BEFORE INSERT ON household_registry
                WHEN NEW.context_type NOT IN ('regular', 'system')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid household context_type');
                END
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_household_context_type_update
                BEFORE UPDATE OF context_type ON household_registry
                WHEN NEW.context_type NOT IN ('regular', 'system')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid household context_type');
                END
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_household_zero_system_insert
                AFTER INSERT ON household_registry
                WHEN CAST(NEW.id AS TEXT) = '0' AND NEW.context_type <> 'system'
                BEGIN
                    UPDATE household_registry
                    SET context_type = 'system'
                    WHERE id = NEW.id;
                END
            """))

    user_columns = _column_names(conn, "app_users")
    if user_columns and "account_status" not in user_columns:
        conn.execute(text(
            "ALTER TABLE app_users "
            "ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'"
        ))
    if user_columns and "password_hash" not in user_columns:
        # Kept nullable until the separately validated credential migration.
        conn.execute(text("ALTER TABLE app_users ADD COLUMN password_hash TEXT"))
    if user_columns:
        conn.execute(text(
            "UPDATE app_users SET account_status = 'active' "
            "WHERE account_status IS NULL OR trim(account_status) = ''"
        ))
        if conn.dialect.name == "sqlite":
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_app_users_account_status_insert
                BEFORE INSERT ON app_users
                WHEN NEW.account_status NOT IN ('active', 'disabled')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid account_status');
                END
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_app_users_account_status_update
                BEFORE UPDATE OF account_status ON app_users
                WHEN NEW.account_status NOT IN ('active', 'disabled')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid account_status');
                END
            """))
