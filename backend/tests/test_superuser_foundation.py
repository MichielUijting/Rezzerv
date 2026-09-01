from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api import superuser_routes
from app.testing.postgresql_onboarding_selftest_fixture import reset_postgresql_test_database
from app.testing.postgresql_platform_authorization_fixture import (
    cleanup_platform_authorization_test_engine,
    create_platform_authorization_test_engine,
)
from tests.support_message_migrated_fixture import migrated_support_migrator_engine


def test_superuser_gate_requires_active_platform_superuser_role(monkeypatch):
    engine = create_platform_authorization_test_engine()
    context = SimpleNamespace(user_id="superuser")
    monkeypatch.setattr(superuser_routes, "resolve_server_session", lambda _conn, _raw: context)

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_platform_user_roles
                SET active = FALSE
                WHERE user_id = 'superuser' AND role_key = 'platform.superuser'
            """))
            with pytest.raises(HTTPException) as exc:
                superuser_routes._require_platform_superuser(conn, "opaque-cookie")
            assert exc.value.status_code == 403

            conn.execute(text("""
                UPDATE auth_platform_user_roles
                SET active = TRUE
                WHERE user_id = 'superuser' AND role_key = 'platform.superuser'
            """))
            granted = superuser_routes._require_platform_superuser(conn, "opaque-cookie")
            assert granted.user_id == "superuser"
    finally:
        cleanup_platform_authorization_test_engine(engine)


def test_inactive_superuser_role_is_denied(monkeypatch):
    engine = create_platform_authorization_test_engine()
    context = SimpleNamespace(user_id="superuser")
    monkeypatch.setattr(superuser_routes, "resolve_server_session", lambda _conn, _raw: context)

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_platform_user_roles
                SET active = FALSE
                WHERE user_id = 'superuser' AND role_key = 'platform.superuser'
            """))
            with pytest.raises(HTTPException) as exc:
                superuser_routes._require_platform_superuser(conn, "opaque-cookie")
            assert exc.value.status_code == 403
    finally:
        cleanup_platform_authorization_test_engine(engine)


def test_superuser_foundation_exposes_read_only_tabs():
    assert superuser_routes.SUPERUSER_TABS == (
        "Overzicht",
        "Huishoudens",
        "Gebruik",
        "Kassabonnen",
        "Systeem",
    )


def test_usage_projection_reads_existing_operational_data_without_new_tracking():
    engine = migrated_support_migrator_engine()
    try:
        with engine.begin() as conn:
            # This focused projection fixture intentionally owns temporary DDL.
            # Use migrator authority; the production/runtime role remains DML-only.
            for table_name in (
                "household_registry",
                "household_memberships",
                "receipt_tables",
                "inventory_events",
                "server_sessions",
            ):
                conn.execute(text(f"DROP TABLE {table_name} CASCADE"))

            conn.execute(text("CREATE TABLE household_registry(id TEXT PRIMARY KEY, naam TEXT, status TEXT)"))
            conn.execute(text("CREATE TABLE household_memberships(household_id TEXT, user_id TEXT, status TEXT)"))
            conn.execute(text("CREATE TABLE receipt_tables(id TEXT PRIMARY KEY, household_id TEXT, created_at TEXT, deleted_at TEXT)"))
            conn.execute(text("CREATE TABLE inventory_events(id TEXT PRIMARY KEY, household_id TEXT, created_at TEXT)"))
            conn.execute(text("CREATE TABLE server_sessions(id TEXT PRIMARY KEY, active_household_id TEXT, updated_at TEXT)"))
            conn.execute(text("INSERT INTO household_registry VALUES ('1', 'Testhuis', 'active')"))
            conn.execute(text("INSERT INTO household_memberships VALUES ('1', 'u1', 'active')"))
            conn.execute(text("INSERT INTO household_memberships VALUES ('1', 'u2', 'inactive')"))
            conn.execute(text("INSERT INTO receipt_tables VALUES ('r1', '1', '2026-08-11T10:00:00', NULL)"))
            conn.execute(text("INSERT INTO receipt_tables VALUES ('r2', '1', '2026-08-11T11:00:00', '2026-08-11T12:00:00')"))
            conn.execute(text("INSERT INTO inventory_events VALUES ('e1', '1', '2026-08-11T12:00:00')"))
            conn.execute(text("INSERT INTO server_sessions VALUES ('s1', '1', '2026-08-11T13:00:00')"))

            payload = superuser_routes._platform_usage(conn)
    finally:
        engine.dispose()
        reset_postgresql_test_database()

    assert payload["access"] == "read_only"
    assert payload["tracking"] == "existing_data_only"
    assert payload["metrics"]["active_households"] == 1
    assert payload["metrics"]["receipt_count"] == 1
    assert payload["metrics"]["inventory_event_count"] == 1
    assert payload["metrics"]["households_with_session_activity"] == 1
    assert payload["items"] == [{
        "household_id": "1",
        "household_name": "Testhuis",
        "active_member_count": 1,
        "receipt_count": 1,
        "inventory_event_count": 1,
        "support_thread_count": 0,
        "last_active_at": "2026-08-11T13:00:00",
    }]
