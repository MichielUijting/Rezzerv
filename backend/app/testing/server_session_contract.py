"""Test-only SQLite fixture for canonical server-session/account context schema.

Production schema authority belongs exclusively to Alembic. Tests that build
small in-memory databases without running the migration chain may opt into this
fixture explicitly instead of relying on production runtime DDL.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def create_server_session_contract_schema(conn: Connection) -> None:
    inspector = inspect(conn)
    user_columns = {str(column.get("name") or "") for column in inspector.get_columns("app_users")}
    if "account_status" not in user_columns:
        conn.execute(text("ALTER TABLE app_users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'"))
    if "password_hash" not in user_columns:
        conn.execute(text("ALTER TABLE app_users ADD COLUMN password_hash TEXT"))

    household_columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_registry")
    }
    if "context_type" not in household_columns:
        conn.execute(text("ALTER TABLE household_registry ADD COLUMN context_type TEXT NOT NULL DEFAULT 'regular'"))
    conn.execute(text("UPDATE household_registry SET context_type = 'system' WHERE CAST(id AS TEXT) = '0'"))

    conn.execute(text("""
        CREATE TABLE frontteam_personal_households (
            user_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE household_onboarding (
            household_id TEXT PRIMARY KEY,
            onboarding_status TEXT NOT NULL DEFAULT 'not_started',
            onboarding_version INTEGER NOT NULL DEFAULT 2,
            primary_use_case TEXT,
            onboarding_step TEXT,
            household_usage_mode TEXT,
            onboarding_completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE server_sessions (
            id VARCHAR(64) PRIMARY KEY,
            session_token_hash VARCHAR(64) NOT NULL UNIQUE,
            user_id VARCHAR(64) NOT NULL,
            active_household_id VARCHAR(64) NULL,
            issued_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            session_version INTEGER NOT NULL DEFAULT 1,
            revoked_at TIMESTAMP NULL,
            replaced_by_session_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE INDEX idx_server_sessions_user_active
        ON server_sessions(user_id, revoked_at, expires_at)
    """))
