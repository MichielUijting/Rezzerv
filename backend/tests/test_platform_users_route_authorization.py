from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api.platform_users_routes import PLATFORM_USERS_SUSPEND_PERMISSION
from app.services.authorization_foundation_service import ROLE_PERMISSIONS
from app.services.platform_user_suspension_service import (
    PlatformUserConflictError,
    ensure_user_account_status_schema,
    install_server_session_suspension_guard,
    list_platform_users,
    require_user_account_active,
    suspend_platform_user,
)
from app.testing.server_session_contract import create_server_session_contract_schema


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_legacy_users(conn):
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            password_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))


def _insert_user(conn, user_id: str, email: str):
    conn.execute(text("""
        INSERT INTO app_users(id, email, password, password_hash)
        VALUES (:id, :email, :password, :password_hash)
    """), {
        "id": user_id,
        "email": email,
        "password": "secret-password-value",
        "password_hash": "secret-password-hash",
    })


def _insert_active_session(conn, *, record_id: str, user_id: str, now: datetime):
    conn.execute(text("""
        INSERT INTO server_sessions(
            id, session_token_hash, user_id, active_household_id,
            issued_at, expires_at, session_version, revoked_at,
            replaced_by_session_id, created_at, updated_at
        ) VALUES (
            :id, :token_hash, :user_id, NULL,
            :issued_at, :expires_at, 1, NULL,
            NULL, :issued_at, :issued_at
        )
    """), {
        "id": record_id,
        "token_hash": f"hash-{record_id}",
        "user_id": user_id,
        "issued_at": now,
        "expires_at": now + timedelta(hours=6),
    })


def test_platform_users_permission_matrix_is_existing_canonical_matrix():
    assert PLATFORM_USERS_SUSPEND_PERMISSION == "platform.users.suspend"
    assert PLATFORM_USERS_SUSPEND_PERMISSION in ROLE_PERMISSIONS["platform.platform_admin"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION in ROLE_PERMISSIONS["platform.ip_owner"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION not in ROLE_PERMISSIONS["platform.superuser"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION not in ROLE_PERMISSIONS["platform.frontteam"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION not in ROLE_PERMISSIONS["platform.support_read"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION not in ROLE_PERMISSIONS["household.admin"]
    assert PLATFORM_USERS_SUSPEND_PERMISSION not in ROLE_PERMISSIONS["household.owner"]


def test_account_status_schema_migrates_existing_users_to_active():
    engine = _engine()
    with engine.begin() as conn:
        _create_legacy_users(conn)
        _insert_user(conn, "user-a", "a@example.test")
        ensure_user_account_status_schema(conn)

        columns = {column["name"] for column in conn.exec_driver_sql("PRAGMA table_info('app_users')").mappings()}
        assert "account_status" in columns
        assert "suspended_at" in columns
        row = conn.execute(text("""
            SELECT account_status, suspended_at FROM app_users WHERE id = 'user-a'
        """)).mappings().one()
        assert row["account_status"] == "active"
        assert row["suspended_at"] is None


def test_user_inventory_is_read_only_safe_projection():
    engine = _engine()
    now = datetime(2026, 8, 24, 19, 30, tzinfo=timezone.utc)
    with engine.begin() as conn:
        _create_legacy_users(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        ensure_user_account_status_schema(conn)
        create_server_session_contract_schema(conn)
        _insert_active_session(conn, record_id="session-target", user_id="target", now=now)

        before = conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()
        items = list_platform_users(conn, current_user_id="actor", now=now)
        after = conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()

        assert before == after == 2
        assert [item["email"] for item in items] == ["actor@example.test", "target@example.test"]
        actor = items[0]
        target = items[1]
        assert actor["is_current"] is True
        assert target["is_current"] is False
        assert target["active_session_count"] == 1
        assert target["account_status"] == "active"
        assert set(target) == {
            "user_id",
            "email",
            "account_status",
            "suspended_at",
            "active_session_count",
            "is_current",
        }
        rendered = repr(items).lower()
        assert "secret-password-value" not in rendered
        assert "secret-password-hash" not in rendered
        assert "session_token_hash" not in rendered
        assert "hash-session-target" not in rendered


def test_suspend_is_atomic_account_authority_and_revokes_all_active_sessions():
    engine = _engine()
    now = datetime(2026, 8, 24, 19, 45, tzinfo=timezone.utc)
    with engine.begin() as conn:
        _create_legacy_users(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        ensure_user_account_status_schema(conn)
        create_server_session_contract_schema(conn)
        _insert_active_session(conn, record_id="session-1", user_id="target", now=now)
        _insert_active_session(conn, record_id="session-2", user_id="target", now=now)

        result = suspend_platform_user(
            conn,
            "target",
            actor_user_id="actor",
            now=now,
        )
        assert result["account_status"] == "suspended"
        assert result["active_sessions_revoked"] == 2

        row = conn.execute(text("""
            SELECT account_status, suspended_at FROM app_users WHERE id = 'target'
        """)).mappings().one()
        assert row["account_status"] == "suspended"
        assert row["suspended_at"] is not None
        assert conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions
            WHERE user_id = 'target' AND revoked_at IS NULL
        """)).scalar_one() == 0

        with pytest.raises(HTTPException) as denied:
            require_user_account_active(conn, "target")
        assert denied.value.status_code == 401


def test_suspend_rejects_self_and_already_suspended_target():
    engine = _engine()
    now = datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        _create_legacy_users(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        ensure_user_account_status_schema(conn)
        create_server_session_contract_schema(conn)

        with pytest.raises(PlatformUserConflictError, match="eigen huidige account"):
            suspend_platform_user(conn, "actor", actor_user_id="actor", now=now)

        suspend_platform_user(conn, "target", actor_user_id="actor", now=now)
        with pytest.raises(PlatformUserConflictError, match="al geschorst"):
            suspend_platform_user(conn, "target", actor_user_id="actor", now=now)


def test_installed_login_guard_rejects_valid_suspended_identity(monkeypatch):
    from app.api import server_session_routes

    engine = _engine()
    with engine.begin() as conn:
        _create_legacy_users(conn)
        _insert_user(conn, "target", "target@example.test")
        ensure_user_account_status_schema(conn)
        conn.execute(text("""
            UPDATE app_users
            SET account_status = 'suspended', suspended_at = CURRENT_TIMESTAMP
            WHERE id = 'target'
        """))

        def fake_resolve_login_identity(_conn, email, password):
            assert email == "target@example.test"
            assert password == "correct-password"
            return {
                "user_id": "target",
                "email": email,
                "active_household_id": None,
                "role": None,
                "platform_system_context": False,
            }

        monkeypatch.setattr(server_session_routes, "_resolve_login_identity", fake_resolve_login_identity)
        monkeypatch.setattr(
            server_session_routes,
            "_platform_user_suspension_guard_installed",
            False,
            raising=False,
        )
        install_server_session_suspension_guard()

        with pytest.raises(HTTPException) as denied:
            server_session_routes._resolve_login_identity(
                conn,
                "target@example.test",
                "correct-password",
            )
        assert denied.value.status_code == 401
        assert "geschorst" in str(denied.value.detail).lower()