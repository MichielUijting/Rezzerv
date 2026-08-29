"""Test-only installer for Alembic-owned authorization/runtime schema contracts.

Production code must never import this module. Isolated SQLite tests can use it
to provision the canonical authorization and session-startup support tables
before exercising runtime validation/seeding behavior.
"""
from __future__ import annotations

from sqlalchemy import text


_AUTHORIZATION_SCHEMA = (
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
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_single_active_ip_owner
    ON auth_platform_user_roles(role_key)
    WHERE role_key = 'platform.ip_owner' AND active = 1
    """,
    """
    CREATE TABLE IF NOT EXISTS frontteam_personal_households (
        user_id TEXT PRIMARY KEY,
        household_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS actor_object_attributions (
        object_type TEXT NOT NULL,
        object_id TEXT NOT NULL,
        household_id TEXT NOT NULL,
        actor_user_id TEXT NOT NULL,
        attribution_source TEXT NOT NULL DEFAULT 'runtime_session',
        first_attributed_at TEXT NOT NULL,
        last_attributed_at TEXT NOT NULL,
        PRIMARY KEY (object_type, object_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_actor_object_attributions_household_actor
    ON actor_object_attributions (household_id, actor_user_id, object_type)
    """,
)


def install_authorization_schema(conn) -> None:
    for statement in _AUTHORIZATION_SCHEMA:
        conn.execute(text(statement))
