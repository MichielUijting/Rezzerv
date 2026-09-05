"""Shared PostgreSQL DML fixtures for account/onboarding and integration tests.

Normal application tests use the canonical Alembic schema. Runtime helpers never
create or alter schema objects and fail closed through the shared PostgreSQL
acceptance boundary. Test-database reset is explicitly a migrator-only operation
and preserves the Alembic version table.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_onboarding_service import ensure_household_onboarding_foundation
from app.testing.onboarding_request_schema_fixture import backfill_completed_household_onboarding
from app.testing.postgresql_acceptance_foundation import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
)


def _columns(conn, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns(table_name)
    }


def seed_household(
    conn,
    *,
    household_id: str,
    name: str,
    context_type: str = "regular",
) -> None:
    columns = _columns(conn, "household_registry")
    id_column = "id" if "id" in columns else "household_id"
    name_column = "naam" if "naam" in columns else "name" if "name" in columns else None
    insert_columns = [id_column]
    insert_values = [":household_id"]
    params = {"household_id": household_id, "name": name, "context_type": context_type}
    if name_column:
        insert_columns.append(name_column)
        insert_values.append(":name")
    if "context_type" in columns:
        insert_columns.append("context_type")
        insert_values.append(":context_type")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO household_registry ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )


def seed_user(
    conn,
    *,
    user_id: str,
    email: str,
    password: str,
) -> None:
    columns = _columns(conn, "app_users")
    id_column = "id" if "id" in columns else "user_id"
    email_column = "email" if "email" in columns else "user_email"
    password_column = "password" if "password" in columns else "password_hash" if "password_hash" in columns else None
    if not password_column:
        raise RuntimeError("app_users mist password/password_hash")
    insert_columns = [id_column, email_column, password_column]
    insert_values = [":user_id", ":email", ":password"]
    params = {"user_id": user_id, "email": email, "password": password}
    if "account_status" in columns:
        insert_columns.append("account_status")
        insert_values.append("'active'")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO app_users ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )


def seed_membership(
    conn,
    *,
    membership_id: str,
    household_id: str,
    user_id: str,
    email: str,
    role: str,
) -> None:
    columns = _columns(conn, "household_memberships")
    insert_columns: list[str] = []
    insert_values: list[str] = []
    params = {
        "membership_id": membership_id,
        "household_id": household_id,
        "user_id": user_id,
        "email": email,
        "role": role,
    }
    if "id" in columns:
        insert_columns.append("id")
        insert_values.append(":membership_id")
    elif "membership_id" in columns:
        insert_columns.append("membership_id")
        insert_values.append(":membership_id")
    insert_columns.append("household_id")
    insert_values.append(":household_id")
    if "user_email" in columns:
        insert_columns.append("user_email")
        insert_values.append(":email")
    elif "email" in columns:
        insert_columns.append("email")
        insert_values.append(":email")
    elif "user_id" in columns:
        insert_columns.append("user_id")
        insert_values.append(":user_id")
    else:
        raise RuntimeError("household_memberships mist user_email/email/user_id")
    role_column = "role" if "role" in columns else "rol" if "rol" in columns else None
    if not role_column:
        raise RuntimeError("household_memberships mist role/rol")
    insert_columns.append(role_column)
    insert_values.append(":role")
    if "status" in columns:
        insert_columns.append("status")
        insert_values.append("'active'")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )
    create_canonical_membership_role(
        conn,
        household_id=household_id,
        membership_id=membership_id,
        legacy_role=role,
    )


def seed_user_membership(
    conn,
    *,
    household_id: str,
    user_id: str,
    email: str,
    password: str,
    membership_id: str,
    role: str,
) -> None:
    seed_user(conn, user_id=user_id, email=email, password=password)
    seed_membership(
        conn,
        membership_id=membership_id,
        household_id=household_id,
        user_id=user_id,
        email=email,
        role=role,
    )


def seed_admin_member_household(
    engine: Engine,
    *,
    household_id: str,
    household_name: str,
    admin_id: str,
    admin_email: str,
    admin_password: str,
    admin_membership_id: str,
    member_id: str,
    member_email: str,
    member_password: str,
    member_membership_id: str,
    onboarding_use_case: str | None = None,
    onboarding_step: str | None = None,
) -> None:
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id=household_id, name=household_name)
        seed_user_membership(
            conn,
            household_id=household_id,
            user_id=admin_id,
            email=admin_email,
            password=admin_password,
            membership_id=admin_membership_id,
            role="admin",
        )
        seed_user_membership(
            conn,
            household_id=household_id,
            user_id=member_id,
            email=member_email,
            password=member_password,
            membership_id=member_membership_id,
            role="member",
        )
        backfill_completed_household_onboarding(conn)
        ensure_household_onboarding_foundation(conn)
        if onboarding_use_case is not None:
            conn.execute(
                text(
                    """
                    UPDATE household_onboarding
                    SET onboarding_status = 'in_progress',
                        primary_use_case = :primary_use_case,
                        onboarding_step = :onboarding_step,
                        onboarding_completed_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE household_id = :household_id
                    """
                ),
                {
                    "household_id": household_id,
                    "primary_use_case": onboarding_use_case,
                    "onboarding_step": onboarding_step,
                },
            )


def seed_completed_legacy_household(
    engine: Engine,
    *,
    household_id: str = "legacy-household",
    household_name: str = "Bestaand huishouden",
) -> None:
    with engine.begin() as conn:
        seed_household(conn, household_id=household_id, name=household_name)
        backfill_completed_household_onboarding(conn)
        ensure_household_onboarding_foundation(conn)
