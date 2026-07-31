from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

HOUSEHOLD_PERMISSIONS = (
    "dashboard.view",
    "notifications.view",
    "notifications.update",
    "inventory.view",
    "inventory.update",
    "inventory.correct",
    "receipts.view",
    "receipts.process",
    "receipts.delete",
    "unpacking.view",
    "unpacking.process",
    "unpacking.correct",
    "almost_out.view",
    "almost_out.update",
    "shopping_list.view",
    "shopping_list.update",
    "shopping_list.manage",
    "articles.view",
    "articles.update",
    "articles.manage",
    "article_groups.view",
    "article_groups.assign",
    "article_groups.manage",
    "locations.view",
    "locations.update",
    "locations.manage",
    "stores.view",
    "stores.update",
    "stores.manage",
    "loyalty.view",
    "loyalty.update",
    "loyalty.manage",
    "insights.view",
    "insights.export",
    "members.view",
    "members.manage",
    "household_settings.view",
    "household_settings.manage",
    "permissions.view",
)

PLATFORM_PERMISSIONS = (
    "platform.households.search",
    "platform.households.view_metadata",
    "platform.households.read_data",
    "platform.support_access.read",
    "platform.support_access.mutate",
    "platform.catalog.view",
    "platform.catalog.update",
    "platform.catalog.manage",
    "platform.external_databases.view",
    "platform.external_databases.update",
    "platform.external_databases.manage",
    "platform.frontteam.manage",
    "platform.users.view",
    "platform.users.suspend",
    "platform.sessions.revoke",
    "platform.audit.view",
    "platform.feature_flags.manage",
)

OWNER_PERMISSIONS = set(HOUSEHOLD_PERMISSIONS)
MEMBER_PERMISSIONS = {
    "dashboard.view", "notifications.view", "notifications.update",
    "inventory.view", "inventory.update", "receipts.view", "receipts.process",
    "unpacking.view", "unpacking.process", "almost_out.view", "almost_out.update",
    "shopping_list.view", "shopping_list.update", "articles.view", "articles.update",
    "article_groups.view", "article_groups.assign", "locations.view", "locations.update",
    "stores.view", "stores.update", "loyalty.view", "loyalty.update", "insights.view",
    "members.view", "household_settings.view", "permissions.view",
}
VIEWER_PERMISSIONS = {key for key in HOUSEHOLD_PERMISSIONS if key.endswith(".view")}

FRONTTEAM_PERMISSIONS = {
    "platform.catalog.view", "platform.catalog.update", "platform.catalog.manage",
    "platform.external_databases.view", "platform.external_databases.update",
    "platform.external_databases.manage",
}

ROLE_PERMISSIONS = {
    "huishouden.kijker": VIEWER_PERMISSIONS,
    "huishouden.lid": MEMBER_PERMISSIONS,
    "huishouden.eigenaar": OWNER_PERMISSIONS,
    "platform.frontteam": FRONTTEAM_PERMISSIONS,
    "platform.supergebruiker": set(PLATFORM_PERMISSIONS),
}

LEGACY_ROLE_MAPPING = {
    "household.viewer": "huishouden.kijker",
    "household.member": "huishouden.lid",
    "household.advanced_member": "huishouden.lid",
    "household.admin": "huishouden.eigenaar",
    "platform.superuser": "platform.supergebruiker",
}

KNOWN_PERMISSIONS = frozenset(HOUSEHOLD_PERMISSIONS + PLATFORM_PERMISSIONS)


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    permission_key: str
    granted_by: str | None = None


def ensure_authorization_foundation(conn) -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS auth_permissions (
            permission_key TEXT PRIMARY KEY,
            scope TEXT NOT NULL CHECK (scope IN ('household', 'platform')),
            description TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_roles (
            role_key TEXT PRIMARY KEY,
            scope TEXT NOT NULL CHECK (scope IN ('household', 'platform')),
            name TEXT NOT NULL,
            system_role INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_role_permissions (
            role_key TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (role_key, permission_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_membership_roles (
            household_id TEXT NOT NULL,
            membership_id TEXT NOT NULL,
            role_key TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (household_id, membership_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_membership_permission_overrides (
            household_id TEXT NOT NULL,
            membership_id TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (household_id, membership_id, permission_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_platform_user_roles (
            user_id TEXT NOT NULL,
            role_key TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, role_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_support_sessions (
            id TEXT PRIMARY KEY,
            support_user_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            access_level TEXT NOT NULL CHECK (access_level IN ('metadata', 'read', 'mutate', 'emergency')),
            reason TEXT NOT NULL,
            ticket_reference TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id TEXT PRIMARY KEY,
            actor_user_id TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            household_id TEXT,
            support_session_id TEXT,
            action TEXT NOT NULL,
            object_type TEXT,
            object_id TEXT,
            old_value TEXT,
            new_value TEXT,
            reason TEXT,
            ticket_reference TEXT,
            created_at TEXT NOT NULL
        )
        """,
    )
    for statement in statements:
        conn.execute(text(statement))
    _seed_registry(conn)
    _migrate_legacy_roles(conn)


def _seed_registry(conn) -> None:
    for key in HOUSEHOLD_PERMISSIONS:
        conn.execute(text("""
            INSERT INTO auth_permissions(permission_key, scope, description)
            VALUES (:key, 'household', :description)
            ON CONFLICT(permission_key) DO UPDATE SET active = 1
        """), {"key": key, "description": key})
    for key in PLATFORM_PERMISSIONS:
        conn.execute(text("""
            INSERT INTO auth_permissions(permission_key, scope, description)
            VALUES (:key, 'platform', :description)
            ON CONFLICT(permission_key) DO UPDATE SET active = 1
        """), {"key": key, "description": key})

    role_names = {
        "huishouden.kijker": "Kijker",
        "huishouden.lid": "Lid",
        "huishouden.eigenaar": "Eigenaar",
        "platform.frontteam": "Frontteam",
        "platform.supergebruiker": "Supergebruiker",
    }
    for role_key, permissions in ROLE_PERMISSIONS.items():
        scope = "household" if role_key.startswith("huishouden.") else "platform"
        conn.execute(text("""
            INSERT INTO auth_roles(role_key, scope, name)
            VALUES (:role_key, :scope, :name)
            ON CONFLICT(role_key) DO UPDATE SET active = 1, name = excluded.name, scope = excluded.scope
        """), {"role_key": role_key, "scope": scope, "name": role_names[role_key]})
        conn.execute(text("DELETE FROM auth_role_permissions WHERE role_key = :role_key"), {"role_key": role_key})
        for permission_key in permissions:
            conn.execute(text("""
                INSERT INTO auth_role_permissions(role_key, permission_key)
                VALUES (:role_key, :permission_key)
                ON CONFLICT(role_key, permission_key) DO NOTHING
            """), {"role_key": role_key, "permission_key": permission_key})

    for legacy_role in LEGACY_ROLE_MAPPING:
        conn.execute(text("UPDATE auth_roles SET active = 0 WHERE role_key = :role_key"), {"role_key": legacy_role})


def _migrate_legacy_roles(conn) -> None:
    for legacy_role, new_role in LEGACY_ROLE_MAPPING.items():
        conn.execute(text("""
            UPDATE auth_membership_roles
            SET role_key = :new_role, updated_at = CURRENT_TIMESTAMP
            WHERE role_key = :legacy_role
        """), {"legacy_role": legacy_role, "new_role": new_role})
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active, created_at, updated_at)
            SELECT user_id, :new_role, active, created_at, CURRENT_TIMESTAMP
            FROM auth_platform_user_roles
            WHERE role_key = :legacy_role
            ON CONFLICT(user_id, role_key) DO UPDATE SET active = excluded.active, updated_at = CURRENT_TIMESTAMP
        """), {"legacy_role": legacy_role, "new_role": new_role})
        conn.execute(text("DELETE FROM auth_platform_user_roles WHERE role_key = :legacy_role"), {"legacy_role": legacy_role})


def evaluate_household_permission(conn, *, household_id: str, membership_id: str, permission_key: str) -> AuthorizationDecision:
    if permission_key not in KNOWN_PERMISSIONS or permission_key.startswith("platform."):
        return AuthorizationDecision(False, "onbekende_of_verkeerde_reikwijdte", permission_key)

    override = conn.execute(text("""
        SELECT effect FROM auth_membership_permission_overrides
        WHERE household_id = :household_id
          AND membership_id = :membership_id
          AND permission_key = :permission_key
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "membership_id": str(membership_id),
        "permission_key": permission_key,
    }).scalar()
    if override == "deny":
        return AuthorizationDecision(False, "expliciet_geweigerd", permission_key)
    if override == "allow":
        return AuthorizationDecision(True, "expliciet_toegestaan", permission_key, "individuele_toestemming")

    role_key = conn.execute(text("""
        SELECT mr.role_key
        FROM auth_membership_roles mr
        JOIN auth_role_permissions rp ON rp.role_key = mr.role_key
        JOIN auth_roles r ON r.role_key = mr.role_key AND r.active = 1
        JOIN auth_permissions p ON p.permission_key = rp.permission_key AND p.active = 1
        WHERE mr.household_id = :household_id
          AND mr.membership_id = :membership_id
          AND mr.active = 1
          AND r.scope = 'household'
          AND p.scope = 'household'
          AND rp.permission_key = :permission_key
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "membership_id": str(membership_id),
        "permission_key": permission_key,
    }).scalar()
    return AuthorizationDecision(bool(role_key), "rol_toegestaan" if role_key else "niet_toegestaan", permission_key, role_key)


def evaluate_platform_permission(conn, *, user_id: str, permission_key: str) -> AuthorizationDecision:
    if permission_key not in KNOWN_PERMISSIONS or not permission_key.startswith("platform."):
        return AuthorizationDecision(False, "onbekende_of_verkeerde_reikwijdte", permission_key)
    role_key = conn.execute(text("""
        SELECT ur.role_key
        FROM auth_platform_user_roles ur
        JOIN auth_role_permissions rp ON rp.role_key = ur.role_key
        JOIN auth_roles r ON r.role_key = ur.role_key AND r.active = 1
        JOIN auth_permissions p ON p.permission_key = rp.permission_key AND p.active = 1
        WHERE lower(ur.user_id) = lower(:user_id)
          AND ur.active = 1
          AND r.scope = 'platform'
          AND p.scope = 'platform'
          AND rp.permission_key = :permission_key
        ORDER BY CASE WHEN ur.role_key = 'platform.supergebruiker' THEN 0 ELSE 1 END
        LIMIT 1
    """), {"user_id": str(user_id), "permission_key": permission_key}).scalar()
    return AuthorizationDecision(bool(role_key), "rol_toegestaan" if role_key else "niet_toegestaan", permission_key, role_key)


def set_frontteam_membership(conn, *, user_id: str, active: bool) -> None:
    ensure_authorization_foundation(conn)
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active, created_at, updated_at)
        VALUES (:user_id, 'platform.frontteam', :active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, role_key) DO UPDATE SET active = excluded.active, updated_at = CURRENT_TIMESTAMP
    """), {"user_id": str(user_id).strip().lower(), "active": 1 if active else 0})


def is_frontteam_member(conn, *, user_id: str) -> bool:
    ensure_authorization_foundation(conn)
    return bool(conn.execute(text("""
        SELECT 1 FROM auth_platform_user_roles
        WHERE lower(user_id) = lower(:user_id)
          AND role_key = 'platform.frontteam'
          AND active = 1
        LIMIT 1
    """), {"user_id": str(user_id)}).first())


def write_authorization_audit(
    conn,
    *,
    actor_user_id: str,
    actor_type: str,
    action: str,
    household_id: str | None = None,
    support_session_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    old_value=None,
    new_value=None,
    reason: str | None = None,
    ticket_reference: str | None = None,
) -> str:
    audit_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(text("""
        INSERT INTO auth_audit_log(
            id, actor_user_id, actor_type, household_id, support_session_id,
            action, object_type, object_id, old_value, new_value,
            reason, ticket_reference, created_at
        ) VALUES (
            :id, :actor_user_id, :actor_type, :household_id, :support_session_id,
            :action, :object_type, :object_id, :old_value, :new_value,
            :reason, :ticket_reference, :created_at
        )
    """), {
        "id": audit_id,
        "actor_user_id": str(actor_user_id),
        "actor_type": actor_type,
        "household_id": str(household_id) if household_id is not None else None,
        "support_session_id": support_session_id,
        "action": action,
        "object_type": object_type,
        "object_id": str(object_id) if object_id is not None else None,
        "old_value": json.dumps(old_value, ensure_ascii=False, sort_keys=True) if old_value is not None else None,
        "new_value": json.dumps(new_value, ensure_ascii=False, sort_keys=True) if new_value is not None else None,
        "reason": reason,
        "ticket_reference": ticket_reference,
        "created_at": created_at,
    })
    return audit_id


def assert_owner_remains(conn, *, household_id: str, membership_id_to_remove: str) -> None:
    current_role = conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = :household_id
          AND membership_id = :membership_id
          AND active = 1
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "membership_id": str(membership_id_to_remove),
    }).scalar()
    if current_role != "huishouden.eigenaar":
        return
    raise ValueError("Draag het eigenaarschap eerst over aan een ander lid.")


# Tijdelijke achterwaartse compatibiliteit voor bestaande aanroepen.
def assert_last_household_admin_remains(conn, *, household_id: str, membership_id_to_remove: str) -> None:
    assert_owner_remains(conn, household_id=household_id, membership_id_to_remove=membership_id_to_remove)
