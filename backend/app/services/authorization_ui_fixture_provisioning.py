from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import ensure_authorization_foundation

AUTHORIZATION_UI_MEMBER_EMAIL = "lid@rezzerv.local"
AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID = "0"
AUTHORIZATION_UI_MEMBERSHIP_ID = "fixture-lid-huishouden-0"
AUTHORIZATION_UI_ROLE_KEY = "household.member"
AUTHORIZATION_UI_LEGACY_ROLE = "member"
AUTHORIZATION_UI_DEFAULT_PASSWORD = "RezzervLid123!"


@dataclass(frozen=True)
class AuthorizationUiFixtureProvisioningResult:
    email: str
    household_id: str
    membership_id: str
    role_key: str


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def ensure_authorization_ui_fixture_member(conn) -> AuthorizationUiFixtureProvisioningResult | None:
    """Provision the deterministic authorization UI member in test household 0.

    The fixture is deliberately unavailable in normal production runtime. It is
    enabled by the same explicit CI/test switch that permits household 0.
    Repeated calls update the existing user and membership instead of creating
    duplicates.
    """

    allow_test_household = str(
        os.getenv("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not allow_test_household:
        return None

    user_columns = _columns(conn, "app_users")
    user_id_column = _pick(user_columns, "id", "user_id")
    user_email_column = _pick(user_columns, "email", "user_email")
    user_password_column = _pick(user_columns, "password", "password_hash")
    if not user_id_column or not user_email_column:
        raise RuntimeError("app_users heeft geen bruikbare id- en e-mailkolommen")

    existing_user = conn.execute(
        text(
            f"SELECT {user_id_column} AS user_id FROM app_users "
            f"WHERE lower({user_email_column}) = lower(:email) LIMIT 1"
        ),
        {"email": AUTHORIZATION_UI_MEMBER_EMAIL},
    ).mappings().first()

    if existing_user:
        user_id = str(existing_user["user_id"])
        if user_password_column:
            conn.execute(
                text(
                    f"UPDATE app_users SET {user_password_column} = :password "
                    f"WHERE {user_id_column} = :user_id"
                ),
                {"password": AUTHORIZATION_UI_DEFAULT_PASSWORD, "user_id": user_id},
            )
    else:
        user_id = AUTHORIZATION_UI_MEMBER_EMAIL
        insert_columns = [user_id_column, user_email_column]
        insert_values = [":user_id", ":email"]
        params = {"user_id": user_id, "email": AUTHORIZATION_UI_MEMBER_EMAIL}
        if user_password_column:
            insert_columns.append(user_password_column)
            insert_values.append(":password")
            params["password"] = AUTHORIZATION_UI_DEFAULT_PASSWORD
        if "created_at" in user_columns:
            insert_columns.append("created_at")
            insert_values.append("CURRENT_TIMESTAMP")
        if "updated_at" in user_columns:
            insert_columns.append("updated_at")
            insert_values.append("CURRENT_TIMESTAMP")
        conn.execute(
            text(
                f"INSERT INTO app_users ({', '.join(insert_columns)}) "
                f"VALUES ({', '.join(insert_values)})"
            ),
            params,
        )

    membership_columns = _columns(conn, "household_memberships")
    membership_id_column = _pick(membership_columns, "id", "membership_id")
    household_column = _pick(membership_columns, "household_id")
    email_column = _pick(membership_columns, "user_email", "email")
    user_column = _pick(membership_columns, "user_id")
    role_column = _pick(membership_columns, "role", "rol")
    status_column = _pick(membership_columns, "status")
    if not household_column or not role_column or (not email_column and not user_column):
        raise RuntimeError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    identity_predicates: list[str] = []
    params = {
        "household_id": AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID,
        "email": AUTHORIZATION_UI_MEMBER_EMAIL,
        "user_id": user_id,
    }
    if email_column:
        identity_predicates.append(f"lower({email_column}) = lower(:email)")
    if user_column:
        identity_predicates.append(f"CAST({user_column} AS TEXT) = :user_id")

    membership_id_expression = membership_id_column or household_column
    existing_membership = conn.execute(
        text(
            f"SELECT {membership_id_expression} AS membership_id "
            f"FROM household_memberships "
            f"WHERE CAST({household_column} AS TEXT) = :household_id "
            f"AND ({' OR '.join(identity_predicates)}) LIMIT 1"
        ),
        params,
    ).mappings().first()

    if existing_membership:
        membership_id = str(existing_membership["membership_id"])
        assignments = [f"{role_column} = :legacy_role"]
        update_params = dict(params)
        update_params["legacy_role"] = AUTHORIZATION_UI_LEGACY_ROLE
        if status_column:
            assignments.append(f"{status_column} = 'active'")
        conn.execute(
            text(
                f"UPDATE household_memberships SET {', '.join(assignments)} "
                f"WHERE CAST({household_column} AS TEXT) = :household_id "
                f"AND ({' OR '.join(identity_predicates)})"
            ),
            update_params,
        )
    else:
        membership_id = AUTHORIZATION_UI_MEMBERSHIP_ID
        insert_columns = [household_column, role_column]
        insert_values = [":household_id", ":legacy_role"]
        insert_params = dict(params)
        insert_params["legacy_role"] = AUTHORIZATION_UI_LEGACY_ROLE
        if membership_id_column:
            insert_columns.insert(0, membership_id_column)
            insert_values.insert(0, ":membership_id")
            insert_params["membership_id"] = membership_id
        if email_column:
            insert_columns.append(email_column)
            insert_values.append(":email")
        if user_column:
            insert_columns.append(user_column)
            insert_values.append(":user_id")
        if status_column:
            insert_columns.append(status_column)
            insert_values.append("'active'")
        if "created_at" in membership_columns:
            insert_columns.append("created_at")
            insert_values.append("CURRENT_TIMESTAMP")
        conn.execute(
            text(
                f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
                f"VALUES ({', '.join(insert_values)})"
            ),
            insert_params,
        )

    ensure_authorization_foundation(conn)
    role_exists = conn.execute(
        text(
            "SELECT 1 FROM auth_membership_roles "
            "WHERE household_id = :household_id AND membership_id = :membership_id LIMIT 1"
        ),
        {
            "household_id": AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID,
            "membership_id": membership_id,
        },
    ).first()
    if role_exists:
        conn.execute(
            text(
                "UPDATE auth_membership_roles "
                "SET role_key = :role_key, active = TRUE "
                "WHERE household_id = :household_id AND membership_id = :membership_id"
            ),
            {
                "household_id": AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID,
                "membership_id": membership_id,
                "role_key": AUTHORIZATION_UI_ROLE_KEY,
            },
        )
    else:
        conn.execute(
            text(
                "INSERT INTO auth_membership_roles "
                "(household_id, membership_id, role_key, active) "
                "VALUES (:household_id, :membership_id, :role_key, TRUE)"
            ),
            {
                "household_id": AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID,
                "membership_id": membership_id,
                "role_key": AUTHORIZATION_UI_ROLE_KEY,
            },
        )

    return AuthorizationUiFixtureProvisioningResult(
        email=AUTHORIZATION_UI_MEMBER_EMAIL,
        household_id=AUTHORIZATION_UI_MEMBER_HOUSEHOLD_ID,
        membership_id=membership_id,
        role_key=AUTHORIZATION_UI_ROLE_KEY,
    )