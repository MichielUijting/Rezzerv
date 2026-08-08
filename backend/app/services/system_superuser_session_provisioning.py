from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import ensure_authorization_foundation

SUPERGEBRUIKER_EMAIL = "supergebruiker@rezzerv.local"
SUPERGEBRUIKER_HUISHOUDEN_ID = "0"
SUPERGEBRUIKER_MEMBERSHIP_ID = "system-supergebruiker-huishouden-0"
SUPERGEBRUIKER_DEFAULT_PASSWORD = "RezzervSuper123!"


@dataclass(frozen=True)
class SystemSuperuserSessionProvisioningResult:
    email: str
    household_id: str
    membership_id: str


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def ensure_system_superuser_for_session_runtime(conn) -> SystemSuperuserSessionProvisioningResult:
    """Provision the canonical fixed superuser on the existing test household 0.

    This mirrors the authorization model introduced in PR #214. Household 0 is
    deliberately created only when the explicit CI/test switch is enabled; a
    normal production runtime must provision it outside this compatibility layer.
    """

    ensure_authorization_foundation(conn)

    allow_test_household = str(
        os.getenv("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}

    household_columns = _columns(conn, "household_registry")
    household_id_column = _pick(household_columns, "id", "household_id")
    household_name_column = _pick(household_columns, "naam", "name")
    if not household_id_column:
        raise RuntimeError("household_registry heeft geen bruikbare identificatiekolom")

    household_exists = conn.execute(
        text(
            f"SELECT 1 FROM household_registry "
            f"WHERE CAST({household_id_column} AS TEXT) = :household_id LIMIT 1"
        ),
        {"household_id": SUPERGEBRUIKER_HUISHOUDEN_ID},
    ).first()
    if not household_exists:
        if not allow_test_household:
            raise RuntimeError(
                "Huishouden 0 ontbreekt; zet REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO alleen in CI/test aan"
            )
        insert_columns = [household_id_column]
        insert_values = [":household_id"]
        params = {"household_id": SUPERGEBRUIKER_HUISHOUDEN_ID}
        if household_name_column:
            insert_columns.append(household_name_column)
            insert_values.append(":household_name")
            params["household_name"] = "Testhuishouden 0"
        if "created_at" in household_columns:
            insert_columns.append("created_at")
            insert_values.append("CURRENT_TIMESTAMP")
        conn.execute(
            text(
                f"INSERT INTO household_registry ({', '.join(insert_columns)}) "
                f"VALUES ({', '.join(insert_values)})"
            ),
            params,
        )

    user_columns = _columns(conn, "app_users")
    user_id_column = _pick(user_columns, "id", "user_id")
    user_email_column = _pick(user_columns, "email", "user_email")
    user_password_column = _pick(user_columns, "password", "password_hash")
    if not user_id_column or not user_email_column or not user_password_column:
        raise RuntimeError("app_users heeft geen bruikbare id-, e-mail- en wachtwoordkolommen")

    password = str(
        os.getenv("REZZERV_SUPERGEBRUIKER_PASSWORD")
        or SUPERGEBRUIKER_DEFAULT_PASSWORD
    ).strip()
    existing_user = conn.execute(
        text(
            f"SELECT {user_id_column} AS user_id FROM app_users "
            f"WHERE lower({user_email_column}) = lower(:email) LIMIT 1"
        ),
        {"email": SUPERGEBRUIKER_EMAIL},
    ).mappings().first()
    if existing_user:
        user_id = str(existing_user["user_id"])
        conn.execute(
            text(
                f"UPDATE app_users SET {user_password_column} = :password "
                f"WHERE {user_id_column} = :user_id"
            ),
            {"password": password, "user_id": user_id},
        )
    else:
        user_id = SUPERGEBRUIKER_EMAIL
        insert_columns = [user_id_column, user_email_column, user_password_column]
        insert_values = [":user_id", ":email", ":password"]
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
            {"user_id": user_id, "email": SUPERGEBRUIKER_EMAIL, "password": password},
        )

    conn.execute(
        text(
            """
            INSERT INTO auth_platform_user_roles
                (user_id, role_key, active, created_at, updated_at)
            VALUES
                (:user_id, 'platform.superuser', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, role_key) DO UPDATE SET
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"user_id": user_id},
    )

    membership_columns = _columns(conn, "household_memberships")
    membership_id_column = _pick(membership_columns, "id", "membership_id")
    membership_household_column = _pick(membership_columns, "household_id")
    membership_email_column = _pick(membership_columns, "user_email", "email")
    membership_user_column = _pick(membership_columns, "user_id")
    membership_role_column = _pick(membership_columns, "role", "rol")
    membership_status_column = _pick(membership_columns, "status")
    if (
        not membership_household_column
        or (not membership_email_column and not membership_user_column)
        or not membership_role_column
    ):
        raise RuntimeError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    identity_predicates = []
    params = {
        "household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
        "email": SUPERGEBRUIKER_EMAIL,
        "user_id": user_id,
    }
    if membership_email_column:
        identity_predicates.append(f"lower({membership_email_column}) = lower(:email)")
    if membership_user_column:
        identity_predicates.append(f"CAST({membership_user_column} AS TEXT) = :user_id")
    existing_membership = conn.execute(
        text(
            f"SELECT "
            f"{membership_id_column if membership_id_column else membership_household_column} AS membership_id "
            f"FROM household_memberships "
            f"WHERE CAST({membership_household_column} AS TEXT) = :household_id "
            f"AND ({' OR '.join(identity_predicates)}) LIMIT 1"
        ),
        params,
    ).mappings().first()

    if existing_membership:
        membership_id = str(existing_membership["membership_id"])
        assignments = [f"{membership_role_column} = 'owner'"]
        if membership_status_column:
            assignments.append(f"{membership_status_column} = 'active'")
        where_parts = [f"CAST({membership_household_column} AS TEXT) = :household_id"]
        where_parts.append(f"({' OR '.join(identity_predicates)})")
        conn.execute(
            text(
                f"UPDATE household_memberships SET {', '.join(assignments)} "
                f"WHERE {' AND '.join(where_parts)}"
            ),
            params,
        )
    else:
        membership_id = SUPERGEBRUIKER_MEMBERSHIP_ID
        insert_columns = [membership_household_column, membership_role_column]
        insert_values = [":household_id", "'owner'"]
        insert_params = dict(params)
        if membership_id_column:
            insert_columns.insert(0, membership_id_column)
            insert_values.insert(0, ":membership_id")
            insert_params["membership_id"] = membership_id
        if membership_email_column:
            insert_columns.append(membership_email_column)
            insert_values.append(":email")
        if membership_user_column:
            insert_columns.append(membership_user_column)
            insert_values.append(":user_id")
        if membership_status_column:
            insert_columns.append(membership_status_column)
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

    return SystemSuperuserSessionProvisioningResult(
        email=SUPERGEBRUIKER_EMAIL,
        household_id=SUPERGEBRUIKER_HUISHOUDEN_ID,
        membership_id=membership_id,
    )
