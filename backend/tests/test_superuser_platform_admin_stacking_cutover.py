from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api.server_session_routes import _resolve_login_identity
from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.platform_authorization_management_service import (
    PLATFORM_ADMIN_ROLE_KEY,
    SUPERUSER_ROLE_KEY,
    grant_special_role,
    revoke_special_role,
)
from app.services.server_session_service import (
    create_none_server_session,
    create_system_server_session,
    public_session_payload,
    resolve_server_session,
)


@pytest.fixture()
def connection():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('0', 'Systeemhuishouden', 'system')
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                user_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY(user_id, household_id)
            )
        """))
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status)
            VALUES
              ('owner', 'owner@example.test', 'owner-secret', 'active'),
              ('stacked', 'stacked@example.test', 'stacked-secret', 'active')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('owner', 'platform.ip_owner', 1)
        """))
        yield conn


def _grant_stack(conn) -> None:
    grant_special_role(
        conn,
        "stacked",
        role_key=SUPERUSER_ROLE_KEY,
        actor_user_id="owner",
    )
    grant_special_role(
        conn,
        "stacked",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )


def test_stacked_login_routes_to_h0_and_projects_permission_union(connection):
    _grant_stack(connection)

    identity = _resolve_login_identity(
        connection,
        "stacked@example.test",
        "stacked-secret",
    )
    assert identity["active_household_id"] == "0"
    assert identity["role"] == "owner"
    assert identity["platform_system_context"] is True

    raw_session_id, created = create_system_server_session(
        connection,
        user_id="stacked",
    )
    resolved = resolve_server_session(connection, raw_session_id)
    payload = public_session_payload(resolved)

    assert created.context_type == resolved.context_type == "system"
    assert created.active_household_id == resolved.active_household_id == "0"
    assert created.is_platform_superuser is resolved.is_platform_superuser is True
    assert created.is_platform_admin is resolved.is_platform_admin is True
    assert payload["is_platform_superuser"] is True
    assert "platform_roles" not in payload

    granted = {key for key, allowed in payload["permissions"].items() if allowed}
    assert set(ROLE_PERMISSIONS[SUPERUSER_ROLE_KEY]) <= granted
    assert set(ROLE_PERMISSIONS[PLATFORM_ADMIN_ROLE_KEY]) <= granted
    assert "platform.special_roles.manage" not in granted

    with pytest.raises(HTTPException) as exc:
        create_none_server_session(connection, user_id="stacked")
    assert exc.value.status_code == 403


def test_revoking_platform_admin_keeps_h0_superuser_session_and_removes_technical_permissions(connection):
    _grant_stack(connection)
    raw_session_id, _ = create_system_server_session(connection, user_id="stacked")

    revoke_special_role(
        connection,
        "stacked",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )

    resolved = resolve_server_session(connection, raw_session_id)
    payload = public_session_payload(resolved)
    assert resolved.context_type == "system"
    assert resolved.is_platform_superuser is True
    assert resolved.is_platform_admin is False
    assert payload["permissions"].get("platform.audit.view") is not True
    assert payload["permissions"].get("platform.feature_flags.manage") is not True


def test_revoking_superuser_invalidates_h0_session_and_next_login_becomes_none_context(connection):
    _grant_stack(connection)
    raw_session_id, _ = create_system_server_session(connection, user_id="stacked")

    revoke_special_role(
        connection,
        "stacked",
        role_key=SUPERUSER_ROLE_KEY,
        actor_user_id="owner",
    )

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_session_id)
    assert exc.value.status_code == 403

    identity = _resolve_login_identity(
        connection,
        "stacked@example.test",
        "stacked-secret",
    )
    assert identity["active_household_id"] is None
    assert identity["role"] is None
    assert identity["platform_system_context"] is False

    _, none_context = create_none_server_session(connection, user_id="stacked")
    none_payload = public_session_payload(none_context)
    assert none_context.context_type == "none"
    assert none_context.is_platform_admin is True
    assert none_payload["context_type"] == "none"
    assert set(ROLE_PERMISSIONS[PLATFORM_ADMIN_ROLE_KEY]) <= {
        key for key, allowed in none_payload["permissions"].items() if allowed
    }


def test_ip_owner_platform_admin_combination_stays_fail_closed(connection):
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('owner', 'platform.platform_admin', 1)
    """))

    with pytest.raises(HTTPException) as login_exc:
        _resolve_login_identity(
            connection,
            "owner@example.test",
            "owner-secret",
        )
    assert login_exc.value.status_code == 403

    with pytest.raises(HTTPException) as session_exc:
        create_system_server_session(
            connection,
            user_id="owner",
        )
    assert session_exc.value.status_code == 403
