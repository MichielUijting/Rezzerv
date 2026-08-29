"""Validation-only runtime contract for roles/account model v2.

Alembic owns the schema and historical normalization. Runtime callers may
validate the contract but must never create, alter, trigger, or repair schema
objects or rows.
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
    """Fail closed unless the Alembic-owned roles-v2 contract is present."""
    household_columns = _column_names(conn, "household_registry")
    required_household = {"id", "context_type"}
    missing_household = required_household - household_columns
    if missing_household:
        raise RuntimeError(
            "household_registry mist canonical roles-v2 kolommen: "
            + ", ".join(sorted(missing_household))
        )

    user_columns = _column_names(conn, "app_users")
    required_users = {"id", "account_status", "password_hash"}
    missing_users = required_users - user_columns
    if missing_users:
        raise RuntimeError(
            "app_users mist canonical roles-v2 kolommen: "
            + ", ".join(sorted(missing_users))
        )

    invalid_household_count = int(conn.execute(text(
        "SELECT COUNT(*) FROM household_registry "
        "WHERE context_type IS NULL OR context_type NOT IN ('regular', 'system')"
    )).scalar_one())
    if invalid_household_count:
        raise RuntimeError("household_registry bevat ongeldige context_type waarden")

    invalid_user_count = int(conn.execute(text(
        "SELECT COUNT(*) FROM app_users "
        "WHERE account_status IS NULL OR account_status NOT IN ('active', 'disabled')"
    )).scalar_one())
    if invalid_user_count:
        raise RuntimeError("app_users bevat ongeldige account_status waarden")
