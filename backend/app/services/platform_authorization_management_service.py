from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import (
    evaluate_platform_permission,
    write_authorization_audit,
)


PLATFORM_ADMIN_ROLE_KEY = "platform.platform_admin"
PLATFORM_PERMISSIONS_MANAGE = "platform.permissions.manage"


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
            "managed_by_this_page": str(row["role_key"]) == PLATFORM_ADMIN_ROLE_KEY,
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


def _safe_user_item(
    row: Mapping[str, Any],
    *,
    current_user_id: str,
    role_keys: list[str],
    effective_permissions: list[str],
) -> dict[str, Any]:
    user_id = str(row.get("id") or "")
    account_status = _normalize_status(row.get("account_status")) or "active"
    has_platform_admin = PLATFORM_ADMIN_ROLE_KEY in role_keys
    is_current = user_id == str(current_user_id or "")
    return {
        "user_id": user_id,
        "email": str(row.get("email") or ""),
        "account_status": account_status,
        "platform_role_keys": list(role_keys),
        "effective_platform_permissions": list(effective_permissions),
        "has_platform_admin": has_platform_admin,
        "is_current": is_current,
        "can_grant_platform_admin": account_status == "active" and not has_platform_admin,
        "can_revoke_platform_admin": has_platform_admin and not is_current,
    }


def list_platform_authorizations(
    conn: Connection,
    *,
    current_user_id: str,
) -> dict[str, Any]:
    role_matrix = _load_platform_role_matrix(conn)
    role_keys_by_user = _role_keys_by_user(conn)
    permissions_by_user = _effective_permissions_by_user(conn)
    users = conn.execute(text("""
        SELECT id, email, account_status
        FROM app_users
        ORDER BY lower(trim(email)) ASC, id ASC
    """)).mappings().all()
    return {
        "users": [
            _safe_user_item(
                row,
                current_user_id=current_user_id,
                role_keys=role_keys_by_user.get(str(row.get("id") or ""), []),
                effective_permissions=permissions_by_user.get(str(row.get("id") or ""), []),
            )
            for row in users
        ],
        "roles": role_matrix,
        "managed_role_key": PLATFORM_ADMIN_ROLE_KEY,
    }


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


def _platform_admin_assignment_active(conn: Connection, user_id: str) -> bool:
    row = conn.execute(text("""
        SELECT 1
        FROM auth_platform_user_roles
        WHERE user_id = :user_id
          AND role_key = :role_key
          AND active = 1
        LIMIT 1
    """), {"user_id": str(user_id), "role_key": PLATFORM_ADMIN_ROLE_KEY}).first()
    return bool(row)


def _active_manage_authority_count(conn: Connection) -> int:
    value = conn.execute(text("""
        SELECT COUNT(DISTINCT ur.user_id)
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        JOIN auth_role_permissions rp ON rp.role_key = ur.role_key
        JOIN auth_permissions p ON p.permission_key = rp.permission_key
        JOIN app_users u ON u.id = ur.user_id
        WHERE ur.active = 1
          AND r.active = 1
          AND r.scope = 'platform'
          AND p.active = 1
          AND p.scope = 'platform'
          AND rp.permission_key = :permission_key
          AND lower(trim(COALESCE(u.account_status, 'active'))) = 'active'
    """), {"permission_key": PLATFORM_PERMISSIONS_MANAGE}).scalar_one()
    return int(value or 0)


def _safe_item_for_user(
    conn: Connection,
    row: Mapping[str, Any],
    *,
    current_user_id: str,
) -> dict[str, Any]:
    user_id = str(row.get("id") or "")
    role_keys = _role_keys_by_user(conn).get(user_id, [])
    permissions = _effective_permissions_by_user(conn).get(user_id, [])
    return _safe_user_item(
        row,
        current_user_id=current_user_id,
        role_keys=role_keys,
        effective_permissions=permissions,
    )


def grant_platform_admin(
    conn: Connection,
    user_id: str,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _load_user(conn, user_id)
    target_user_id = str(row["id"])
    if _normalize_status(row.get("account_status")) != "active":
        raise PlatformAuthorizationConflictError(
            "Een geschorst account kan geen Platformbeheerder worden"
        )
    if _platform_admin_assignment_active(conn, target_user_id):
        raise PlatformAuthorizationConflictError("Gebruiker is al Platformbeheerder")

    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES (:user_id, :role_key, 1)
        ON CONFLICT(user_id, role_key) DO UPDATE SET
            active = 1,
            updated_at = CURRENT_TIMESTAMP
    """), {"user_id": target_user_id, "role_key": PLATFORM_ADMIN_ROLE_KEY})
    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="platform_user",
        action="platform.role.granted",
        object_type="platform_user_role",
        object_id=target_user_id,
        old_value=None,
        new_value={"role_key": PLATFORM_ADMIN_ROLE_KEY},
        reason="platform.permissions.manage",
    )
    return _safe_item_for_user(conn, row, current_user_id=str(actor_user_id))


def revoke_platform_admin(
    conn: Connection,
    user_id: str,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _load_user(conn, user_id)
    target_user_id = str(row["id"])
    normalized_actor_user_id = str(actor_user_id or "").strip()
    if target_user_id == normalized_actor_user_id:
        raise PlatformAuthorizationConflictError(
            "Je kunt je eigen Platformbeheerder-rol hier niet intrekken"
        )
    if not _platform_admin_assignment_active(conn, target_user_id):
        raise PlatformAuthorizationConflictError("Gebruiker is geen Platformbeheerder")

    conn.execute(text("""
        UPDATE auth_platform_user_roles
        SET active = 0, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND role_key = :role_key
    """), {"user_id": target_user_id, "role_key": PLATFORM_ADMIN_ROLE_KEY})

    if _active_manage_authority_count(conn) < 1:
        raise PlatformAuthorizationConflictError(
            "Minimaal één actief account met platform.permissions.manage moet behouden blijven"
        )

    write_authorization_audit(
        conn,
        actor_user_id=normalized_actor_user_id,
        actor_type="platform_user",
        action="platform.role.revoked",
        object_type="platform_user_role",
        object_id=target_user_id,
        old_value={"role_key": PLATFORM_ADMIN_ROLE_KEY},
        new_value=None,
        reason="platform.permissions.manage",
    )
    return _safe_item_for_user(conn, row, current_user_id=normalized_actor_user_id)


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
