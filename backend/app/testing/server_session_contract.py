"""Test-only SQLite fixture for the canonical server_sessions contract.

Production schema authority belongs exclusively to Alembic. Tests that build
small in-memory databases without running the migration chain may opt into this
fixture explicitly instead of relying on production runtime DDL.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def create_server_session_contract_schema(conn: Connection) -> None:
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
