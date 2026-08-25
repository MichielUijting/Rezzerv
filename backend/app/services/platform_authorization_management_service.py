from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import (
    evaluate_platform_permission,
    write_authorization_audit,
)
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE,
    ensure_frontteam_personal_household_for_user,
    frontteam_personal_household_id,
    resolve_frontteam_personal_household_id,
)


SUPERUSER_ROLE_KEY = "platform.superuser"
FRONTTEAM_ROLE_KEY = "platform.frontteam"
PLATFORM_ADMIN_ROLE_KEY = "platform.platform_admin"
IP_OWNER_ROLE_KEY = "platform.ip_owner"
MANAGED_SPECIAL_ROLE_KEYS = (
    SUPERUSER_ROLE_KEY,
    FRONTTEAM_ROLE_KEY,
    PLATFORM_ADMIN_ROLE_KEY,
)
PLATFORM_PERMISSIONS_MANAGE = "platform.permissions.manage"
PLATFORM_SPECIAL_ROLES_MANAGE = "platform.special_roles.manage"


class PlatformAuthorizationNotFoundError(LookupError):
    pass


class PlatformAuthorizationConflictError(RuntimeError):
    pass


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _load_platform_role_matrix(conn: Connection) -> list[dict[str, Any]]:
    role_rows = conn.execute(text("""
        SELECT role_key, name
        FROM auth_roles
        WHERE scope = 'platform' AND active = 1
        ORDER BY role_key
    """)).mappings().all()
    permission_rows = conn.execute(text("""
        SELECT rp.role_key, rp.permission_key
        FROM auth_role_permissions rp
        JOIN auth_permissions p ON p.permission_key = rp.permission_key
        WHERE p.scope = 'platform' AND p.active = 1
        ORDER BY rp.role_key, rp.permission_key
    """)).mappings().all()
    permissions_by_role: dict[str, list[str]] = {}
    for row in permission_rows:
        permissions_by_role.setdefault(str(row["role_key"]), []).append(
            str(row["permission_key"])
        )

    return [
        {
            "role_key": str(row["role_key"]),
            "name": str(row["name"]),
            "permissions": permissions_by_role.get(str(row["role_key"]), []),
            "managed_by_this_page": str(row["role_key"]) in MANAGED_SPECIAL_ROLE_KEYS,
            "protected": str(row["role_key"]) == IP_OWNER_ROLE_KEY,
        }
        for row in role_rows
    ]


def _role_keys_by_user(conn: Connection) -> dict[str, list[str]]:
    rows = conn.execute(text("""
        SELECT ur.user_id, ur.role_key
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        WHERE ur.active = 1 AND r.active = 1 AND r.scope = 'platform'
        ORDER BY ur.user_id, ur.role_key
    """)).mappings().all()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(str(row["user_id"]), []).append(str(row["role_key"]))
    return result


def _effective_permissions_by_user(conn: Connection) -> dict[str, list[str]]:
    rows = conn.execute(text("""
        SELECT DISTINCT ur.user_id, rp.permission_key
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        JOIN auth_role_permissions rp ON rp.role_key = ur.role_key
        JOIN auth_permissions p ON p.permission_key = rp.permission_key
        WHERE ur.active = 1
          AND r.active = 1
          AND r.scope = 'platform'
          AND p.active = 1
          AND p.scope = 'platform'
        ORDER BY ur.user_id, rp.permission_key
    """)).mappings().all()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(str(row["user_id"]), []).append(str(row["permission_key"]))
    return result


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "").strip().lower() for column in inspector.get_columns(table_name)}


def _load_user(conn: Connection, user_id: str) -> Mapping[str, Any]:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise PlatformAuthorizationNotFoundError("Gebruiker ontbreekt")
    row = conn.execute(text("""
        SELECT id, email, account_status
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).mappings().first()
    if not row:
        raise PlatformAuthorizationNotFoundError("Gebruiker niet gevonden")
    return row


def _active_regular_household_ids(conn: Connection, user_id: str) -> list[str]:
    membership_columns = _table_columns(conn, "household_memberships")
    if not membership_columns:
        return []
    user = _load_user(conn, user_id)
    params: dict[str, Any] = {"user_id": str(user["id"]), "email": str(user.get("email") or "")}
    if "user_id" in membership_columns:
        identity = "CAST(hm.user_id AS TEXT) = :user_id"
    elif "user_email" in membership_columns:
        identity = "lower(trim(hm.user_email)) = lower(trim(:email))"
    else:
        return []
    predicates = [identity]
    if "status" in membership_columns:
        predicates.append("lower(trim(COALESCE(hm.status, 'active'))) IN ('active', 'actief', 'accepted', 'geaccepteerd')")
    if "active" in membership_columns:
        predicates.append("COALESCE(hm.active, 1) = 1")
    registry_columns = _table_columns(conn, "household_registry")
    if {"id", "context_type"} <= registry_columns:
        join = "JOIN household_registry hr ON CAST(hr.id AS TEXT) = CAST(hm.household_id AS TEXT)"
        predicates.append("lower(trim(hr.context_type)) = 'regular'")
    else:
        join = ""
        predicates.append("CAST(hm.household_id AS TEXT) <> '0'")
    rows = conn.execute(text(f"""
        SELECT DISTINCT CAST(hm.household_id AS TEXT) AS household_id
        FROM household_memberships hm
        {join}
        WHERE {' AND '.join(predicates)}
        ORDER BY household_id
    """), params).scalars().all()
    return [str(value) for value in rows]


def _role_assignment_active(conn: Connection, user_id: str, role_key: str) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM auth_platform_user_roles
        WHERE user_id = :user_id AND role_key = :role_key AND active = 1
        LIMIT 1
    """), {"user_id": str(user_id), "role_key": str(role_key)}).first()
    return bool(row)


def _grant_block_reason(
    conn: Connection,
    row: Mapping[str, Any],
    *,
    role_key: str,
    active_role_keys: set[str],
) -> str | None:
    if role_key not in MANAGED_SPECIAL_ROLE_KEYS:
        return "Deze rol wordt hier niet beheerd"
    if IP_OWNER_ROLE_KEY in active_role_keys:
        return "IP-eigenaar is beschermd tegen regulier rolbeheer"
    if _normalize_status(row.get("account_status")) != "active":
        return "Een geschorst account kan geen speciale rol krijgen"
    if role_key in active_role_keys:
        return "Rol is al actief"

    if role_key == FRONTTEAM_ROLE_KEY:
        if active_role_keys & {SUPERUSER_ROLE_KEY, PLATFORM_ADMIN_ROLE_KEY, IP_OWNER_ROLE_KEY}:
            return "Frontteamlid kan niet met een systeem- of Platformbeheerderrol worden gecombineerd"
        target_user_id = str(row["id"])
        mapped_household_id = resolve_frontteam_personal_household_id(conn, target_user_id)
        personal_household_id = str(
            mapped_household_id or frontteam_personal_household_id(target_user_id)
        )
        unrelated = [
            household_id
            for household_id in _active_regular_household_ids(conn, target_user_id)
            if household_id != personal_household_id
        ]
        if unrelated:
            return "Frontteamlid vereist een eigen persoonlijk huishouden zonder andere actieve huishoudlidmaatschappen"
        return None

    if FRONTTEAM_ROLE_KEY in active_role_keys:
        return "Superuser en Platformbeheerder kunnen niet met Frontteamlid worden gecombineerd"
    if _active_regular_household_ids(conn, str(row["id"])):
        return "Superuser en Platformbeheerder hebben geen regulier huishoudlidmaatschap"
    return None


def _revoke_block_reason(role_key: str, active_role_keys: set[str]) -> str | None:
    if role_key not in MANAGED_SPECIAL_ROLE_KEYS:
        return "Deze rol wordt hier niet beheerd"
    if IP_OWNER_ROLE_KEY in active_role_keys:
        return "IP-eigenaar is beschermd tegen regulier rolbeheer"
    if role_key not in active_role_keys:
        return "Rol is niet actief"
    return None


def _role_actions(
    conn: Connection,
    row: Mapping[str, Any],
    *,
    role_keys: list[str],
    can_manage_special_roles: bool,
) -> dict[str, dict[str, Any]]:
    active_role_keys = set(role_keys)
    result: dict[str, dict[str, Any]] = {}
    for role_key in MANAGED_SPECIAL_ROLE_KEYS:
        grant_reason = _grant_block_reason(
            conn,
            row,
            role_key=role_key,
            active_role_keys=active_role_keys,
        )
        revoke_reason = _revoke_block_reason(role_key, active_role_keys)
        result[role_key] = {
            "active": role_key in active_role_keys,
            "can_grant": bool(can_manage_special_roles and grant_reason is None),
            "can_revoke": bool(can_manage_special_roles and revoke_reason is None),
            "grant_blocked_reason": None if can_manage_special_roles else "Alleen de IP-eigenaar beheert speciale rollen",
            "revoke_blocked_reason": None if can_manage_special_roles else "Alleen de IP-eigenaar beheert speciale rollen",
        }
        if can_manage_special_roles:
            result[role_key]["grant_blocked_reason"] = grant_reason
            result[role_key]["revoke_blocked_reason"] = revoke_reason
    return result


def _safe_user_item(
    conn: Connection,
    row: Mapping[str, Any],
    *,
    current_user_id: str,
    role_keys: list[str],
    effective_permissions: list[str],
    can_manage_special_roles: bool,
) -> dict[str, Any]:
    user_id = str(row.get("id") or "")
    account_status = _normalize_status(row.get("account_status")) or "active"
    return {
        "user_id": user_id,
        "email": str(row.get("email") or ""),
        "account_status": account_status,
        "platform_role_keys": list(role_keys),
        "effective_platform_permissions": list(effective_permissions),
        "is_current": user_id == str(current_user_id or ""),
        "is_ip_owner": IP_OWNER_ROLE_KEY in role_keys,
        "role_actions": _role_actions(
            conn,
            row,
            role_keys=role_keys,
            can_manage_special_roles=can_manage_special_roles,
        ),
    }


def list_platform_authorizations(
    conn: Connection,
    *,
    current_user_id: str,
) -> dict[str, Any]:
    role_matrix = _load_platform_role_matrix(conn)
    role_keys_by_user = _role_keys_by_user(conn)
    permissions_by_user = _effective_permissions_by_user(conn)
    can_manage_special_roles = evaluate_platform_permission(
        conn,
        user_id=str(current_user_id),
        permission_key=PLATFORM_SPECIAL_ROLES_MANAGE,
    ).allowed
    users = conn.execute(text("""
        SELECT id, email, account_status
        FROM app_users
        ORDER BY lower(trim(email)) ASC, id ASC
    """)).mappings().all()
    return {
        "users": [
            _safe_user_item(
                conn,
                row,
                current_user_id=current_user_id,
                role_keys=role_keys_by_user.get(str(row.get("id") or ""), []),
                effective_permissions=permissions_by_user.get(str(row.get("id") or ""), []),
                can_manage_special_roles=can_manage_special_roles,
            )
            for row in users
        ],
        "roles": role_matrix,
        "inventory_permission": PLATFORM_PERMISSIONS_MANAGE,
        "special_roles_permission": PLATFORM_SPECIAL_ROLES_MANAGE,
        "managed_role_keys": list(MANAGED_SPECIAL_ROLE_KEYS),
        "can_manage_special_roles": can_manage_special_roles,
    }


def _safe_item_for_user(
    conn: Connection,
    row: Mapping[str, Any],
    *,
    current_user_id: str,
) -> dict[str, Any]:
    user_id = str(row.get("id") or "")
    role_keys = _role_keys_by_user(conn).get(user_id, [])
    permissions = _effective_permissions_by_user(conn).get(user_id, [])
    can_manage_special_roles = evaluate_platform_permission(
        conn,
        user_id=str(current_user_id),
        permission_key=PLATFORM_SPECIAL_ROLES_MANAGE,
    ).allowed
    return _safe_user_item(
        conn,
        row,
        current_user_id=current_user_id,
        role_keys=role_keys,
        effective_permissions=permissions,
        can_manage_special_roles=can_manage_special_roles,
    )


def grant_special_role(
    conn: Connection,
    user_id: str,
    *,
    role_key: str,
    actor_user_id: str,
) -> dict[str, Any]:
    normalized_role_key = str(role_key or "").strip()
    if normalized_role_key not in MANAGED_SPECIAL_ROLE_KEYS:
        raise PlatformAuthorizationConflictError("Deze speciale rol wordt hier niet beheerd")
    row = _load_user(conn, user_id)
    target_user_id = str(row["id"])
    active_role_keys = set(_role_keys_by_user(conn).get(target_user_id, []))
    block_reason = _grant_block_reason(
        conn,
        row,
        role_key=normalized_role_key,
        active_role_keys=active_role_keys,
    )
    if block_reason:
        raise PlatformAuthorizationConflictError(block_reason)

    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES (:user_id, :role_key, 1)
        ON CONFLICT(user_id, role_key) DO UPDATE SET
            active = 1,
            updated_at = CURRENT_TIMESTAMP
    """), {"user_id": target_user_id, "role_key": normalized_role_key})

    if normalized_role_key == FRONTTEAM_ROLE_KEY:
        ensure_frontteam_personal_household_for_user(
            conn,
            user_id=target_user_id,
            email=str(row.get("email") or ""),
        )

    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="platform_user",
        action="platform.role.granted",
        object_type="platform_user_role",
        object_id=target_user_id,
        old_value=None,
        new_value={"role_key": normalized_role_key},
        reason=PLATFORM_SPECIAL_ROLES_MANAGE,
    )
    return _safe_item_for_user(conn, row, current_user_id=str(actor_user_id))


def revoke_special_role(
    conn: Connection,
    user_id: str,
    *,
    role_key: str,
    actor_user_id: str,
) -> dict[str, Any]:
    normalized_role_key = str(role_key or "").strip()
    if normalized_role_key not in MANAGED_SPECIAL_ROLE_KEYS:
        raise PlatformAuthorizationConflictError("Deze speciale rol wordt hier niet beheerd")
    row = _load_user(conn, user_id)
    target_user_id = str(row["id"])
    active_role_keys = set(_role_keys_by_user(conn).get(target_user_id, []))
    block_reason = _revoke_block_reason(normalized_role_key, active_role_keys)
    if block_reason:
        raise PlatformAuthorizationConflictError(block_reason)

    conn.execute(text("""
        UPDATE auth_platform_user_roles
        SET active = 0, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND role_key = :role_key
    """), {"user_id": target_user_id, "role_key": normalized_role_key})

    if normalized_role_key == FRONTTEAM_ROLE_KEY:
        mapped_household_id = resolve_frontteam_personal_household_id(
            conn,
            target_user_id,
        )
        if mapped_household_id:
            expected_household_id = frontteam_personal_household_id(target_user_id)
            if str(mapped_household_id) != expected_household_id:
                raise PlatformAuthorizationConflictError(
                    "Frontteam-persoonlijk huishouden wijkt af van canonieke identiteit"
                )
            conn.execute(text(f"""
                DELETE FROM {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE}
                WHERE user_id = :user_id
            """), {"user_id": target_user_id})

    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="platform_user",
        action="platform.role.revoked",
        object_type="platform_user_role",
        object_id=target_user_id,
        old_value={"role_key": normalized_role_key},
        new_value=None,
        reason=PLATFORM_SPECIAL_ROLES_MANAGE,
    )
    return _safe_item_for_user(conn, row, current_user_id=str(actor_user_id))


def grant_platform_admin(
    conn: Connection,
    user_id: str,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    return grant_special_role(
        conn,
        user_id,
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id=actor_user_id,
    )


def revoke_platform_admin(
    conn: Connection,
    user_id: str,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    return revoke_special_role(
        conn,
        user_id,
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id=actor_user_id,
    )


def user_has_platform_permission(
    conn: Connection,
    *,
    user_id: str,
    permission_key: str,
) -> bool:
    return evaluate_platform_permission(
        conn,
        user_id=str(user_id),
        permission_key=str(permission_key),
    ).allowed
