"""Provision the dedicated regular household for active Frontteam users.

Frontteam remains a platform role for authorization, but receives a normal
regular household context for day-to-day app usage. The reserved household is
never an authority source by itself: an active ``platform.frontteam`` role is
still required by the server-session policy on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.roles_v2_schema_foundation import (
    HOUSEHOLD_CONTEXT_REGULAR,
    ensure_roles_v2_account_and_household_foundation,
)

FRONTTEAM_HOUSEHOLD_ID = "frontteam"
FRONTTEAM_HOUSEHOLD_NAME = "Frontteam"
FRONTTEAM_PLATFORM_ROLE = "platform.frontteam"
FRONTTEAM_HOUSEHOLD_ROLE_KEY = "household.admin"
FRONTTEAM_LEGACY_ROLE = "admin"


@dataclass(frozen=True)
class FrontteamHouseholdProvisioningResult:
    household_id: str
    active_frontteam_users: int
    memberships_created: int
    memberships_updated: int


def _columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _frontteam_membership_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv:frontteam:{user_id}"))


def _ensure_frontteam_household(conn: Connection) -> None:
    ensure_roles_v2_account_and_household_foundation(conn)
    columns = _columns(conn, "household_registry")
    id_column = _pick(columns, "id", "household_id")
    name_column = _pick(columns, "naam", "name")
    if not id_column:
        raise RuntimeError("household_registry heeft geen bruikbare identificatiekolom")

    existing = conn.execute(
        text(
            f"SELECT 1 FROM household_registry "
            f"WHERE CAST({id_column} AS TEXT) = :household_id LIMIT 1"
        ),
        {"household_id": FRONTTEAM_HOUSEHOLD_ID},
    ).first()

    if existing:
        assignments: list[str] = []
        params = {"household_id": FRONTTEAM_HOUSEHOLD_ID}
        if "context_type" in columns:
            assignments.append("context_type = :context_type")
            params["context_type"] = HOUSEHOLD_CONTEXT_REGULAR
        if name_column:
            assignments.append(f"{name_column} = :household_name")
            params["household_name"] = FRONTTEAM_HOUSEHOLD_NAME
        if "updated_at" in columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
        if assignments:
            conn.execute(
                text(
                    f"UPDATE household_registry SET {', '.join(assignments)} "
                    f"WHERE CAST({id_column} AS TEXT) = :household_id"
                ),
                params,
            )
        return

    insert_columns = [id_column]
    insert_values = [":household_id"]
    params: dict[str, object] = {"household_id": FRONTTEAM_HOUSEHOLD_ID}
    if name_column:
        insert_columns.append(name_column)
        insert_values.append(":household_name")
        params["household_name"] = FRONTTEAM_HOUSEHOLD_NAME
    if "context_type" in columns:
        insert_columns.append("context_type")
        insert_values.append(":context_type")
        params["context_type"] = HOUSEHOLD_CONTEXT_REGULAR
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO household_registry ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )


def _active_frontteam_users(conn: Connection) -> list[dict[str, str]]:
    rows = conn.execute(text("""
        SELECT u.id AS user_id, u.email AS email
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        JOIN app_users u ON u.id = ur.user_id
        WHERE ur.role_key = :role_key
          AND ur.active = 1
          AND r.active = 1
          AND r.scope = 'platform'
        ORDER BY u.id
    """), {"role_key": FRONTTEAM_PLATFORM_ROLE}).mappings().all()
    return [
        {
            "user_id": str(row.get("user_id") or "").strip(),
            "email": str(row.get("email") or "").strip(),
        }
        for row in rows
        if str(row.get("user_id") or "").strip()
    ]


def _ensure_frontteam_membership(
    conn: Connection,
    *,
    user_id: str,
    email: str,
) -> tuple[str, bool]:
    columns = _columns(conn, "household_memberships")
    membership_id_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    email_column = _pick(columns, "user_email", "email")
    user_column = _pick(columns, "user_id")
    role_column = _pick(columns, "role", "rol")
    status_column = _pick(columns, "status", "membership_status")
    active_column = _pick(columns, "active", "is_active")
    if not household_column or not role_column or (not email_column and not user_column):
        raise RuntimeError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    identity_predicates: list[str] = []
    params: dict[str, object] = {
        "household_id": FRONTTEAM_HOUSEHOLD_ID,
        "user_id": user_id,
        "email": email,
    }
    if user_column:
        identity_predicates.append(f"CAST({user_column} AS TEXT) = :user_id")
    if email_column:
        identity_predicates.append(f"lower(trim({email_column})) = lower(trim(:email))")

    membership_id_expression = (
        f"CAST({membership_id_column} AS TEXT)"
        if membership_id_column
        else (f"CAST({user_column} AS TEXT)" if user_column else f"CAST({email_column} AS TEXT)")
    )
    existing = conn.execute(
        text(
            f"SELECT {membership_id_expression} AS membership_id "
            f"FROM household_memberships "
            f"WHERE CAST({household_column} AS TEXT) = :household_id "
            f"AND ({' OR '.join(identity_predicates)}) LIMIT 1"
        ),
        params,
    ).mappings().first()

    created = existing is None
    if existing:
        membership_id = str(existing.get("membership_id") or "").strip()
        assignments = [f"{role_column} = :legacy_role"]
        update_params = dict(params)
        update_params["legacy_role"] = FRONTTEAM_LEGACY_ROLE
        if status_column:
            assignments.append(f"{status_column} = 'active'")
        if active_column:
            assignments.append(f"{active_column} = 1")
        if "updated_at" in columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
        conn.execute(
            text(
                f"UPDATE household_memberships SET {', '.join(assignments)} "
                f"WHERE CAST({household_column} AS TEXT) = :household_id "
                f"AND ({' OR '.join(identity_predicates)})"
            ),
            update_params,
        )
    else:
        membership_id = (
            _frontteam_membership_id(user_id)
            if membership_id_column
            else (user_id if user_column else email)
        )
        insert_columns = [household_column, role_column]
        insert_values = [":household_id", ":legacy_role"]
        insert_params = dict(params)
        insert_params["legacy_role"] = FRONTTEAM_LEGACY_ROLE
        if membership_id_column:
            insert_columns.insert(0, membership_id_column)
            insert_values.insert(0, ":membership_id")
            insert_params["membership_id"] = membership_id
        if user_column:
            insert_columns.append(user_column)
            insert_values.append(":user_id")
        if email_column:
            insert_columns.append(email_column)
            insert_values.append(":email")
        if status_column:
            insert_columns.append(status_column)
            insert_values.append("'active'")
        if active_column:
            insert_columns.append(active_column)
            insert_values.append("1")
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
            insert_params,
        )

    conn.execute(text("""
        INSERT INTO auth_membership_roles(
            household_id, membership_id, role_key, active, updated_at
        ) VALUES (
            :household_id, :membership_id, :role_key, 1, CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key = excluded.role_key,
            active = 1,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": FRONTTEAM_HOUSEHOLD_ID,
        "membership_id": membership_id,
        "role_key": FRONTTEAM_HOUSEHOLD_ROLE_KEY,
    })
    return membership_id, created


def ensure_frontteam_household_for_session_runtime(
    conn: Connection,
) -> FrontteamHouseholdProvisioningResult:
    """Ensure the dedicated regular Frontteam household and admin memberships.

    This function never assigns ``platform.frontteam``. It only projects an
    already active platform role into the dedicated regular household.
    """

    ensure_authorization_foundation(conn)
    _ensure_frontteam_household(conn)
    users = _active_frontteam_users(conn)
    created = updated = 0
    for user in users:
        _, was_created = _ensure_frontteam_membership(
            conn,
            user_id=user["user_id"],
            email=user["email"],
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return FrontteamHouseholdProvisioningResult(
        household_id=FRONTTEAM_HOUSEHOLD_ID,
        active_frontteam_users=len(users),
        memberships_created=created,
        memberships_updated=updated,
    )
