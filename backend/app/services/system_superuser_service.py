from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    evaluate_household_permission,
    evaluate_platform_permission,
    write_authorization_audit,
)
from app.services.platform_actor_service import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)

SUPERGEBRUIKER_MEMBERSHIP_ID = "system-supergebruiker-huishouden-0"
SUPERGEBRUIKER_DEFAULT_PASSWORD = "RezzervSuper123!"


class SystemSuperuserProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class SystemSuperuserProvisioningResult:
    email: str
    household_id: str
    membership_id: str
    account_created: bool
    membership_created: bool
    roles_changed: bool


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _password(explicit_password: str | None) -> str:
    value = str(
        explicit_password
        or os.getenv("REZZERV_SUPERGEBRUIKER_PASSWORD")
        or SUPERGEBRUIKER_DEFAULT_PASSWORD
    ).strip()
    if len(value) < 12:
        raise SystemSuperuserProvisioningError("Het Supergebruikerswachtwoord moet minimaal 12 tekens bevatten")
    return value


def _require_household_zero(conn) -> None:
    columns = _columns(conn, "household_registry")
    id_column = _pick(columns, "id", "household_id", "huishouden_id")
    if not id_column:
        raise SystemSuperuserProvisioningError("household_registry heeft geen bruikbare identificatiekolom")
    exists = conn.execute(
        text(f"SELECT 1 FROM household_registry WHERE CAST({id_column} AS TEXT) = :household_id LIMIT 1"),
        {"household_id": SUPERGEBRUIKER_HUISHOUDEN_ID},
    ).first()
    if not exists:
        raise SystemSuperuserProvisioningError(
            "Huishouden 0 ontbreekt; de Supergebruikersvoorziening maakt het testhuishouden niet zelf aan"
        )


def _ensure_account(conn, password: str) -> bool:
    columns = _columns(conn, "app_users")
    id_column = _pick(columns, "id", "user_id")
    email_column = _pick(columns, "email", "email_address", "user_email")
    password_column = _pick(columns, "password", "password_hash")
    if not id_column or not email_column or not password_column:
        raise SystemSuperuserProvisioningError("app_users heeft geen bruikbare id-, e-mail- en wachtwoordkolommen")

    existing = conn.execute(
        text(f"SELECT {id_column} AS user_id FROM app_users WHERE lower({email_column}) = lower(:email) LIMIT 1"),
        {"email": SUPERGEBRUIKER_EMAIL},
    ).mappings().first()
    if existing:
        assignments = [f"{password_column} = :password"]
        if "updated_at" in columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
        conn.execute(
            text(f"UPDATE app_users SET {', '.join(assignments)} WHERE lower({email_column}) = lower(:email)"),
            {"email": SUPERGEBRUIKER_EMAIL, "password": password},
        )
        return False

    insert_columns = [id_column, email_column, password_column]
    insert_values = [":id", ":email", ":password"]
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(f"INSERT INTO app_users ({', '.join(insert_columns)}) VALUES ({', '.join(insert_values)})"),
        {"id": SUPERGEBRUIKER_EMAIL, "email": SUPERGEBRUIKER_EMAIL, "password": password},
    )
    return True


def _ensure_membership(conn) -> tuple[str, bool]:
    columns = _columns(conn, "household_memberships")
    membership_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    email_column = _pick(columns, "user_email", "email", "member_email")
    user_column = _pick(columns, "user_id", "app_user_id")
    role_column = _pick(columns, "role", "rol")
    status_column = _pick(columns, "status", "membership_status")
    active_column = _pick(columns, "active", "is_active")
    if not membership_column or not household_column or (not email_column and not user_column):
        raise SystemSuperuserProvisioningError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    identity_predicates = []
    params = {
        "email": SUPERGEBRUIKER_EMAIL,
        "household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
    }
    if email_column:
        identity_predicates.append(f"lower({email_column}) = lower(:email)")
    if user_column:
        identity_predicates.append(f"CAST({user_column} AS TEXT) = :email")
    row = conn.execute(
        text(
            f"SELECT {membership_column} AS membership_id FROM household_memberships "
            f"WHERE CAST({household_column} AS TEXT) = :household_id "
            f"AND ({' OR '.join(identity_predicates)}) LIMIT 1"
        ),
        params,
    ).mappings().first()

    if row:
        membership_id = str(row["membership_id"])
        assignments = []
        update_params = {"membership_id": membership_id}
        if role_column:
            assignments.append(f"{role_column} = 'owner'")
        if status_column:
            assignments.append(f"{status_column} = 'active'")
        if active_column:
            assignments.append(f"{active_column} = 1")
        if "updated_at" in columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
        if assignments:
            conn.execute(
                text(f"UPDATE household_memberships SET {', '.join(assignments)} WHERE {membership_column} = :membership_id"),
                update_params,
            )
        return membership_id, False

    insert_columns = [membership_column, household_column]
    insert_values = [":membership_id", ":household_id"]
    insert_params = {
        "membership_id": SUPERGEBRUIKER_MEMBERSHIP_ID,
        "household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
        "email": SUPERGEBRUIKER_EMAIL,
    }
    if email_column:
        insert_columns.append(email_column)
        insert_values.append(":email")
    if user_column:
        insert_columns.append(user_column)
        insert_values.append(":email")
    if role_column:
        insert_columns.append(role_column)
        insert_values.append("'owner'")
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
        text(f"INSERT INTO household_memberships ({', '.join(insert_columns)}) VALUES ({', '.join(insert_values)})"),
        insert_params,
    )
    return SUPERGEBRUIKER_MEMBERSHIP_ID, True


def ensure_fixed_system_superuser(
    conn,
    *,
    password: str | None = None,
    actor_user_id: str = "system:supergebruiker-provisioning",
) -> SystemSuperuserProvisioningResult:
    """Richt de vaste Supergebruiker in boven op het bestaande huishouden 0."""
    _require_household_zero(conn)
    resolved_password = _password(password)
    account_created = _ensure_account(conn, resolved_password)
    membership_id, membership_created = _ensure_membership(conn)

    ensure_authorization_foundation(conn)

    old_household_role = conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = :household_id AND membership_id = :membership_id
        LIMIT 1
    """), {
        "household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
        "membership_id": membership_id,
    }).scalar()
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key, active, updated_at)
        VALUES (:household_id, :membership_id, 'huishouden.eigenaar', 1, CURRENT_TIMESTAMP)
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key = 'huishouden.eigenaar', active = 1, updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
        "membership_id": membership_id,
    })

    old_platform_roles = set(conn.execute(text("""
        SELECT role_key FROM auth_platform_user_roles
        WHERE lower(user_id) = lower(:user_id) AND active = 1
    """), {"user_id": SUPERGEBRUIKER_EMAIL}).scalars().all())

    conn.execute(text("""
        UPDATE auth_platform_user_roles
        SET active = 0, updated_at = CURRENT_TIMESTAMP
        WHERE role_key = 'platform.supergebruiker'
          AND lower(user_id) <> lower(:user_id)
    """), {"user_id": SUPERGEBRUIKER_EMAIL})
    for role_key in ("platform.supergebruiker", "platform.frontteam"):
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active, created_at, updated_at)
            VALUES (:user_id, :role_key, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, role_key) DO UPDATE SET active = 1, updated_at = CURRENT_TIMESTAMP
        """), {"user_id": SUPERGEBRUIKER_EMAIL, "role_key": role_key})

    roles_changed = (
        old_household_role != "huishouden.eigenaar"
        or not {"platform.supergebruiker", "platform.frontteam"}.issubset(old_platform_roles)
    )
    if account_created or membership_created or roles_changed:
        write_authorization_audit(
            conn,
            actor_user_id=actor_user_id,
            actor_type="systeem",
            household_id=SUPERGEBRUIKER_HUISHOUDEN_ID,
            action="Vaste Supergebruiker ingericht",
            object_type="systeemgebruiker",
            object_id=SUPERGEBRUIKER_EMAIL,
            old_value={
                "huishoudrol": old_household_role,
                "centrale_rollen": sorted(old_platform_roles),
            },
            new_value={
                "huishoudrol": "huishouden.eigenaar",
                "centrale_rollen": ["platform.frontteam", "platform.supergebruiker"],
            },
        )

    household_decision = evaluate_household_permission(
        conn,
        household_id=SUPERGEBRUIKER_HUISHOUDEN_ID,
        membership_id=membership_id,
        permission_key="inventory.update",
    )
    platform_decision = evaluate_platform_permission(
        conn,
        user_id=SUPERGEBRUIKER_EMAIL,
        permission_key="platform.users.view",
    )
    if not household_decision.allowed or not platform_decision.allowed:
        raise SystemSuperuserProvisioningError("De vaste Supergebruiker kon niet end-to-end worden geverifieerd")

    return SystemSuperuserProvisioningResult(
        email=SUPERGEBRUIKER_EMAIL,
        household_id=SUPERGEBRUIKER_HUISHOUDEN_ID,
        membership_id=membership_id,
        account_created=account_created,
        membership_created=membership_created,
        roles_changed=roles_changed,
    )
