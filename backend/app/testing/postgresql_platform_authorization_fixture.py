"""PostgreSQL-only fixture for platform authorization integration tests.

The normal platform authorization tests must exercise the same database engine as
production. Schema authority remains with Alembic; this helper only seeds and
cleans test data in the existing canonical authorization tables.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import ensure_authorization_foundation


_TEST_PLATFORM_ROLES = {
    "superuser": "platform.superuser",
    "ip-owner": "platform.ip_owner",
    "support-reader": "platform.support_read",
    "platform-admin": "platform.platform_admin",
    "frontteam": "platform.frontteam",
}


def create_platform_authorization_test_engine() -> Engine:
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL ontbreekt voor PostgreSQL-autorisatietests")

    engine = create_engine(database_url, future=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise RuntimeError(
            "Platform-autorisatietests vereisen PostgreSQL; "
            f"ontvangen dialect={engine.dialect.name}"
        )

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        for user_id, role_key in _TEST_PLATFORM_ROLES.items():
            conn.execute(
                text(
                    """
                    INSERT INTO auth_platform_user_roles(
                        user_id, role_key, active, created_at, updated_at
                    ) VALUES (
                        :user_id, :role_key, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(user_id, role_key) DO UPDATE SET
                        active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {"user_id": user_id, "role_key": role_key},
            )
    return engine


def cleanup_platform_authorization_test_engine(engine: Engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM auth_platform_user_roles
                    WHERE user_id IN (
                        'superuser', 'ip-owner', 'support-reader',
                        'platform-admin', 'frontteam'
                    )
                    """
                )
            )
    finally:
        engine.dispose()
