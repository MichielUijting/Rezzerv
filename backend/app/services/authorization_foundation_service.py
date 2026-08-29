from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import inspect, text

HOUSEHOLD_PERMISSIONS = (
    "dashboard.view",
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
    "permissions.manage",
    "catalog.view",
    "catalog.update",
    "catalog.manage",
    "gpc.view",
    "gpc.update",
    "gpc.manage",
    "admin.access",
    "frontteam.external_databases.access",
)

PLATFORM_PERMISSIONS = (
    "platform.households.search",
    "platform.households.view_metadata",
    "platform.support_access.request",
    "platform.support_access.activate",
    "platform.support_access.read",
    "platform.support_access.mutate",
    "platform.users.suspend",
    "platform.sessions.revoke",
    "platform.audit.view",
    "platform.permissions.manage",
    "platform.feature_flags.manage",
)

V2_PLATFORM_PERMISSIONS = (
    "platform.system_household.access",
    "platform.special_roles.manage",
    "platform.frontteam_messages.create",
    "platform.frontteam_messages.read",
    "platform.frontteam_messages.reply",
    "platform.frontteam_polls.respond",
    "platform.frontteam_messages.manage",
    "platform.frontteam_polls.manage",
    "platform.frontteam_polls.results.view",
    "platform.external_products.view",
    "platform.external_products.search",
    "platform.external_products.link_existing",
    "platform.catalog.view",
    "platform.catalog.update",
    "platform.catalog.manage",
    "platform.gpc.view",
    "platform.gpc.update",
    "platform.gpc.manage",
    "platform.external_sources.view",
    "platform.external_sources.manage",
    "platform.diagnostics.view",
    "platform.logs.view",
    "platform.integrations.manage",
    "platform.background_jobs.manage",
    "platform.recovery.manage",
    "platform.technical_configuration.manage",
    "platform.test_fixtures.manage",
)

MEMBER_PERMISSIONS = {
    "dashboard.view", "notifications.update",
    "inventory.view", "inventory.update", "inventory.correct",
    "receipts.view", "receipts.process", "receipts.delete",
    "unpacking.view", "unpacking.process", "unpacking.correct",
    "almost_out.view", "almost_out.update",
    "shopping_list.view", "shopping_list.update", "shopping_list.manage",
    "articles.view",
    "article_groups.view", "article_groups.assign",
    "locations.view",
    "stores.view", "stores.update", "stores.manage",
    "loyalty.view", "loyalty.update", "loyalty.manage",
    "insights.view",
    "members.view", "household_settings.view", "permissions.view",
    "catalog.view", "gpc.view",
}

ADMIN_PERMISSIONS = MEMBER_PERMISSIONS | {
    "articles.update", "articles.manage",
    "article_groups.manage",
    "locations.update", "locations.manage",
    "insights.export",
    "members.manage", "household_settings.manage", "permissions.manage",
    "gpc.update", "gpc.manage",
    "admin.access",
}

FRONTTEAM_PERMISSIONS = set(HOUSEHOLD_PERMISSIONS)
SUPERUSER_HOUSEHOLD_PERMISSIONS = set(HOUSEHOLD_PERMISSIONS)

FRONTTEAM_PLATFORM_PERMISSIONS = {
    "platform.frontteam_messages.create",
    "platform.frontteam_messages.read",
    "platform.frontteam_messages.reply",
    "platform.frontteam_polls.respond",
    "platform.external_products.view",
    "platform.external_products.search",
    "platform.external_products.link_existing",
}

V2_SUPERUSER_TARGET_PERMISSIONS = {
    "platform.households.search",
    "platform.households.view_metadata",
    "platform.support_access.request",
    "platform.support_access.activate",
    "platform.support_access.read",
    "platform.support_access.mutate",
    "platform.system_household.access",
    "platform.frontteam_messages.read",
    "platform.frontteam_messages.reply",
    "platform.frontteam_messages.manage",
    "platform.frontteam_polls.manage",
    "platform.frontteam_polls.results.view",
    "platform.external_products.view",
    "platform.external_products.search",
    "platform.external_products.link_existing",
    "platform.catalog.view",
    "platform.catalog.update",
    "platform.catalog.manage",
    "platform.gpc.view",
    "platform.gpc.update",
    "platform.gpc.manage",
    "platform.external_sources.view",
    "platform.external_sources.manage",
}

# Canonical runtime grantset from 9.1.8a onward. The v2 target is no longer
# target-only: ordinary platform.superuser sessions and seeded role grants use it.
ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS = set(V2_SUPERUSER_TARGET_PERMISSIONS)

# Deprecated compatibility alias for older regression imports. It intentionally
# resolves to the active v2 set and must not be used as a separate authority source.
ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS = ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS

PLATFORM_ADMIN_PERMISSIONS = {
    "platform.diagnostics.view",
    "platform.logs.view",
    "platform.audit.view",
    "platform.integrations.manage",
    "platform.background_jobs.manage",
    "platform.recovery.manage",
    "platform.technical_configuration.manage",
    "platform.test_fixtures.manage",
    "platform.sessions.revoke",
    "platform.users.suspend",
    "platform.permissions.manage",
    "platform.feature_flags.manage",
}

IP_OWNER_PERMISSIONS = (
    V2_SUPERUSER_TARGET_PERMISSIONS
    | PLATFORM_ADMIN_PERMISSIONS
    | {"platform.special_roles.manage"}
)

ROLE_PERMISSIONS = {
    "household.viewer": {key for key in HOUSEHOLD_PERMISSIONS if key.endswith(".view")},
    "household.member": set(MEMBER_PERMISSIONS),
    "household.advanced_member": set(ADMIN_PERMISSIONS),
    "household.admin": set(ADMIN_PERMISSIONS),
    "household.owner": set(SUPERUSER_HOUSEHOLD_PERMISSIONS),
    "household.frontteam": set(FRONTTEAM_PERMISSIONS),
    "platform.support_read": {
        "platform.households.search", "platform.households.view_metadata",
        "platform.support_access.request", "platform.support_access.activate",
        "platform.support_access.read", "platform.audit.view",
    },
    "platform.frontteam": set(FRONTTEAM_PLATFORM_PERMISSIONS),
    "platform.superuser": set(ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS),
    "platform.platform_admin": set(PLATFORM_ADMIN_PERMISSIONS),
    "platform.ip_owner": set(IP_OWNER_PERMISSIONS),
}

KNOWN_PERMISSIONS = frozenset(
    HOUSEHOLD_PERMISSIONS + PLATFORM_PERMISSIONS + V2_PLATFORM_PERMISSIONS
)


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    permission_key: str


def permissions_for_session_role(role: str, *, platform_superuser: bool = False) -> set[str]:
    normalized = str(role or "").strip().lower()
    role_key = {
        "viewer": "household.viewer",
        "lid": "household.member",
        "member": "household.member",
        "advanced_member": "household.advanced_member",
        "beheerder": "household.admin",
        "admin": "household.admin",
        "owner": "household.owner",
        "frontteam": "household.frontteam",
        "frontteamlid": "household.frontteam",
    }.get(normalized, "")
    permissions = set(ROLE_PERMISSIONS.get(role_key, set()))
    if platform_superuser:
        permissions.update(ROLE_PERMISSIONS["platform.superuser"])
    return permissions


def resolve_active_platform_role_keys(conn, user_id: str) -> frozenset[str]:
    """Return only active, registered platform roles for one server-side user."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return frozenset()
    rows = conn.execute(text("""
        SELECT ur.role_key
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        WHERE ur.user_id = :user_id
          AND ur.active IS TRUE
          AND r.active IS TRUE
          AND r.scope = 'platform'
        ORDER BY ur.role_key
    """), {"user_id": normalized_user_id}).scalars().all()
    return frozenset(str(role_key) for role_key in rows)


_AUTHORIZATION_FOUNDATION_COLUMNS = {
    "auth_permissions": {"permission_key", "scope", "description", "active", "created_at"},
    "auth_roles": {"role_key", "scope", "name", "system_role", "active", "created_at"},
    "auth_role_permissions": {"role_key", "permission_key", "created_at"},
    "auth_membership_roles": {
        "household_id", "membership_id", "role_key", "active", "created_at", "updated_at",
    },
    "auth_membership_permission_overrides": {
        "household_id", "membership_id", "permission_key", "effect", "reason", "created_at", "updated_at",
    },
    "auth_platform_user_roles": {"user_id", "role_key", "active", "created_at", "updated_at"},
    "auth_support_sessions": {
        "id", "support_user_id", "household_id", "access_level", "reason", "ticket_reference",
        "starts_at", "expires_at", "revoked_at", "created_at",
    },
    "auth_audit_log": {
        "id", "actor_user_id", "actor_type", "household_id", "support_session_id", "action",
        "object_type", "object_id", "old_value", "new_value", "reason", "ticket_reference", "created_at",
    },
}
_AUTHORIZATION_IP_OWNER_INDEX = "idx_auth_single_active_ip_owner"


def validate_authorization_foundation_schema(conn) -> None:
    """Fail closed when Alembic has not installed the authorization contract."""
    inspector = inspect(conn)
    available_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(_AUTHORIZATION_FOUNDATION_COLUMNS) - available_tables)
    if missing_tables:
        raise RuntimeError(
            "Authorization foundation is niet gemigreerd; ontbrekende tabellen: "
            + ", ".join(missing_tables)
        )

    for table_name, required_columns in _AUTHORIZATION_FOUNDATION_COLUMNS.items():
        actual_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"Authorization foundation schema drift voor {table_name}; "
                f"ontbrekende kolommen: {', '.join(missing_columns)}"
            )

    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes("auth_platform_user_roles")
    }
    ip_owner_index = indexes.get(_AUTHORIZATION_IP_OWNER_INDEX)
    if not ip_owner_index:
        raise RuntimeError(
            f"Authorization foundation index ontbreekt: {_AUTHORIZATION_IP_OWNER_INDEX}"
        )
    if not bool(ip_owner_index.get("unique")) or tuple(ip_owner_index.get("column_names") or ()) != ("role_key",):
        raise RuntimeError(
            "Authorization foundation IP-owner index wijkt af in uniqueness/kolommen"
        )


def ensure_authorization_foundation(conn) -> None:
    """Validate Alembic-owned schema and seed canonical registry rows using DML only."""
    validate_authorization_foundation_schema(conn)
    _seed_registry(conn)

def _seed_registry(conn) -> None:
    for key in HOUSEHOLD_PERMISSIONS:
        conn.execute(text("""
            INSERT INTO auth_permissions(permission_key, scope, description)
            VALUES (:key, 'household', :description)
            ON CONFLICT(permission_key) DO UPDATE SET active = TRUE
        """), {"key": key, "description": key})
    for key in PLATFORM_PERMISSIONS + V2_PLATFORM_PERMISSIONS:
        conn.execute(text("""
            INSERT INTO auth_permissions(permission_key, scope, description)
            VALUES (:key, 'platform', :description)
            ON CONFLICT(permission_key) DO UPDATE SET active = TRUE
        """), {"key": key, "description": key})
    role_names = {
        "household.viewer": "Viewer",
        "household.member": "Lid",
        "household.advanced_member": "Gevorderd lid",
        "household.admin": "Huishoudbeheerder",
        "household.owner": "Superuser-huishoudrol",
        "household.frontteam": "Frontteamlid",
        "platform.support_read": "Supportmedewerker lezen",
        "platform.frontteam": "Frontteamlid",
        "platform.superuser": "Platform-superuser",
        "platform.platform_admin": "Platformbeheerder",
        "platform.ip_owner": "IP-eigenaar",
    }
    for role_key, permissions in ROLE_PERMISSIONS.items():
        scope = role_key.split(".", 1)[0]
        conn.execute(text("""
            INSERT INTO auth_roles(role_key, scope, name)
            VALUES (:role_key, :scope, :name)
            ON CONFLICT(role_key) DO UPDATE SET active = TRUE, name = excluded.name
        """), {"role_key": role_key, "scope": scope, "name": role_names[role_key]})
        conn.execute(text("DELETE FROM auth_role_permissions WHERE role_key = :role_key"), {"role_key": role_key})
        for permission_key in sorted(permissions):
            conn.execute(text("""
                INSERT INTO auth_role_permissions(role_key, permission_key)
                VALUES (:role_key, :permission_key)
            """), {"role_key": role_key, "permission_key": permission_key})


def evaluate_household_permission(conn, *, household_id: str, membership_id: str, permission_key: str) -> AuthorizationDecision:
    if permission_key not in KNOWN_PERMISSIONS or permission_key.startswith("platform."):
        return AuthorizationDecision(False, "unknown_or_wrong_scope", permission_key)
    override = conn.execute(text("""
        SELECT effect FROM auth_membership_permission_overrides
        WHERE household_id = :household_id AND membership_id = :membership_id
          AND permission_key = :permission_key LIMIT 1
    """), {"household_id": str(household_id), "membership_id": str(membership_id), "permission_key": permission_key}).scalar()
    if override == "deny":
        return AuthorizationDecision(False, "explicit_deny", permission_key)
    if override == "allow":
        return AuthorizationDecision(True, "explicit_allow", permission_key)
    role_grant = conn.execute(text("""
        SELECT 1 FROM auth_membership_roles mr
        JOIN auth_role_permissions rp ON rp.role_key = mr.role_key
        JOIN auth_roles r ON r.role_key = mr.role_key AND r.active IS TRUE
        JOIN auth_permissions p ON p.permission_key = rp.permission_key AND p.active IS TRUE
        WHERE mr.household_id = :household_id AND mr.membership_id = :membership_id
          AND mr.active IS TRUE AND r.scope = 'household' AND p.scope = 'household'
          AND rp.permission_key = :permission_key LIMIT 1
    """), {"household_id": str(household_id), "membership_id": str(membership_id), "permission_key": permission_key}).first()
    return AuthorizationDecision(bool(role_grant), "role_grant" if role_grant else "not_granted", permission_key)


def evaluate_platform_permission(conn, *, user_id: str, permission_key: str) -> AuthorizationDecision:
    if permission_key not in KNOWN_PERMISSIONS or not permission_key.startswith("platform."):
        return AuthorizationDecision(False, "unknown_or_wrong_scope", permission_key)
    granted = conn.execute(text("""
        SELECT 1 FROM auth_platform_user_roles ur
        JOIN auth_role_permissions rp ON rp.role_key = ur.role_key
        JOIN auth_roles r ON r.role_key = ur.role_key AND r.active IS TRUE
        JOIN auth_permissions p ON p.permission_key = rp.permission_key AND p.active IS TRUE
        WHERE ur.user_id = :user_id AND ur.active IS TRUE AND r.scope = 'platform'
          AND p.scope = 'platform' AND rp.permission_key = :permission_key LIMIT 1
    """), {"user_id": str(user_id), "permission_key": permission_key}).first()
    return AuthorizationDecision(bool(granted), "role_grant" if granted else "not_granted", permission_key)


def write_authorization_audit(conn, *, actor_user_id: str, actor_type: str, action: str,
                              household_id: str | None = None, support_session_id: str | None = None,
                              object_type: str | None = None, object_id: str | None = None,
                              old_value=None, new_value=None, reason: str | None = None,
                              ticket_reference: str | None = None) -> str:
    audit_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(text("""
        INSERT INTO auth_audit_log(id, actor_user_id, actor_type, household_id, support_session_id,
          action, object_type, object_id, old_value, new_value, reason, ticket_reference, created_at)
        VALUES (:id, :actor_user_id, :actor_type, :household_id, :support_session_id,
          :action, :object_type, :object_id, :old_value, :new_value, :reason, :ticket_reference, :created_at)
    """), {
        "id": audit_id, "actor_user_id": str(actor_user_id), "actor_type": actor_type,
        "household_id": str(household_id) if household_id is not None else None,
        "support_session_id": support_session_id, "action": action, "object_type": object_type,
        "object_id": str(object_id) if object_id is not None else None,
        "old_value": json.dumps(old_value, ensure_ascii=False, sort_keys=True) if old_value is not None else None,
        "new_value": json.dumps(new_value, ensure_ascii=False, sort_keys=True) if new_value is not None else None,
        "reason": reason, "ticket_reference": ticket_reference, "created_at": created_at,
    })
    return audit_id


def assert_last_household_admin_remains(conn, *, household_id: str, membership_id_to_remove: str) -> None:
    current_role = conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = :household_id AND membership_id = :membership_id AND active IS TRUE LIMIT 1
    """), {"household_id": str(household_id), "membership_id": str(membership_id_to_remove)}).scalar()
    if current_role not in {"household.admin", "household.owner", "household.frontteam"}:
        return
    remaining = conn.execute(text("""
        SELECT COUNT(*) FROM auth_membership_roles
        WHERE household_id = :household_id AND membership_id <> :membership_id
          AND role_key IN ('household.admin', 'household.owner', 'household.frontteam') AND active IS TRUE
    """), {"household_id": str(household_id), "membership_id": str(membership_id_to_remove)}).scalar_one()
    if int(remaining or 0) < 1:
        raise ValueError("Een huishouden moet minimaal één actieve beheerder behouden.")