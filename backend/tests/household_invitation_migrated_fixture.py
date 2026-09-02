from __future__ import annotations

from sqlalchemy import inspect, text

from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
)

HEAD_REVISION = "20260902_01"


def migrated_postgresql_engine():
    """Return a clean canonical PostgreSQL test engine at the locked Alembic head."""
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != HEAD_REVISION:
        engine.dispose()
        raise AssertionError(f"Expected Alembic revision {HEAD_REVISION}, got {revision}")
    return engine


def insert_user(conn, *, user_id: str, email: str) -> None:
    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("app_users")
    }
    values: dict[str, object] = {"id": user_id, "email": email}
    if "password" in columns:
        values["password"] = "invitation-test-password"
    if "account_status" in columns:
        values["account_status"] = "active"
    column_sql = ", ".join(values)
    bind_sql = ", ".join(f":{column}" for column in values)
    conn.execute(text(f"INSERT INTO app_users ({column_sql}) VALUES ({bind_sql})"), values)


def insert_membership(
    conn,
    *,
    membership_id: str,
    household_id: str,
    user_id: str,
    email: str,
    role: str,
) -> None:
    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_memberships")
    }

    def pick(*candidates: str) -> str | None:
        return next((candidate for candidate in candidates if candidate in columns), None)

    membership_column = pick("id", "membership_id")
    household_column = pick("household_id", "huishouden_id")
    user_column = pick("user_id")
    email_column = pick("user_email", "email")
    role_column = pick("role", "rol")
    status_column = pick("status", "membership_status")
    active_column = pick("active", "is_active")
    if not membership_column or not household_column or (not user_column and not email_column):
        raise AssertionError("Gemigreerde household_memberships mist bruikbare fixture-identiteit")

    values: dict[str, object] = {
        membership_column: membership_id,
        household_column: household_id,
    }
    if user_column:
        values[user_column] = user_id
    if email_column:
        values[email_column] = email
    if role_column:
        values[role_column] = role
    if status_column:
        values[status_column] = "active"
    if active_column:
        values[active_column] = True
    column_sql = ", ".join(values)
    bind_sql = ", ".join(f":{column}" for column in values)
    conn.execute(text(f"INSERT INTO household_memberships ({column_sql}) VALUES ({bind_sql})"), values)
