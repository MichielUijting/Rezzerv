from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import support_broadcast_routes, support_message_routes
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.testing.authorization_schema_fixture import install_authorization_schema


READ_PERMISSION = "platform.support_access.read"
MUTATE_PERMISSION = "platform.support_access.mutate"


@pytest.fixture
def auth_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('superuser', 'platform.superuser', 1),
              ('ip-owner', 'platform.ip_owner', 1),
              ('support-reader', 'platform.support_read', 1),
              ('platform-admin', 'platform.platform_admin', 1),
              ('frontteam', 'platform.frontteam', 1)
        """))
    try:
        yield engine
    finally:
        engine.dispose()


def _context(user_id: str) -> ServerSessionContext:
    now = datetime.now(timezone.utc)
    if user_id in {"superuser", "ip-owner"}:
        context_type = "system"
        household_id = "0"
        role = "owner"
    elif user_id == "platform-admin":
        context_type = "none"
        household_id = None
        role = None
    else:
        context_type = "regular"
        household_id = "household-1"
        role = "admin" if user_id == "ordinary-admin" else "member"
    return ServerSessionContext(
        session_id=f"session-{user_id}",
        user_id=user_id,
        email=f"{user_id}@example.test",
        active_household_id=household_id,
        context_type=context_type,
        role=role,
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        is_platform_superuser=user_id == "superuser",
        is_frontteam=user_id == "frontteam",
    )


def _bind_context(monkeypatch, auth_engine, user_id: str) -> ServerSessionContext:
    context = _context(user_id)
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        lambda: context,
    )
    return context


@pytest.mark.parametrize(
    ("user_id", "permission_key", "allowed"),
    [
        ("superuser", READ_PERMISSION, True),
        ("superuser", MUTATE_PERMISSION, True),
        ("ip-owner", READ_PERMISSION, True),
        ("ip-owner", MUTATE_PERMISSION, True),
        ("support-reader", READ_PERMISSION, True),
        ("support-reader", MUTATE_PERMISSION, False),
        ("platform-admin", READ_PERMISSION, False),
        ("platform-admin", MUTATE_PERMISSION, False),
        ("frontteam", READ_PERMISSION, False),
        ("frontteam", MUTATE_PERMISSION, False),
        ("ordinary-admin", READ_PERMISSION, False),
        ("ordinary-admin", MUTATE_PERMISSION, False),
    ],
)
def test_platform_permission_session_helper_uses_registered_permission_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    permission_key,
    allowed,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        actual_context = session_request_context.require_platform_permission_from_session(
            permission_key,
            "Bearer forged-legacy-token",
        )
        assert actual_context is expected_context
        assert actual_context.user_id == user_id
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            permission_key,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {permission_key}"


def test_invalid_server_session_status_is_preserved(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        invalid_session,
    )

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(READ_PERMISSION)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_role_revocation_is_effective_on_next_permission_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "superuser")

    assert (
        session_request_context.require_platform_permission_from_session(
            READ_PERMISSION
        ).user_id
        == "superuser"
    )

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'superuser'
              AND role_key = 'platform.superuser'
        """))

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(READ_PERMISSION)

    assert exc.value.status_code == 403


def test_support_message_platform_actor_uses_permission_helper_without_legacy_admin_gate(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "support-reader")
    monkeypatch.setattr(
        support_message_routes,
        "_main_module",
        lambda: (_ for _ in ()).throw(AssertionError("legacy main gate was called")),
    )

    actor = support_message_routes._platform_actor(
        "Bearer forged-legacy-token",
        READ_PERMISSION,
    )
    assert actor["user_id"] == "support-reader"

    with pytest.raises(HTTPException) as exc:
        support_message_routes._platform_actor(
            "Bearer forged-legacy-token",
            MUTATE_PERMISSION,
        )
    assert exc.value.status_code == 403


def test_support_broadcast_requires_mutate_permission_without_legacy_admin_gate(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "support-reader")
    monkeypatch.setattr(
        support_broadcast_routes,
        "_main_module",
        lambda: (_ for _ in ()).throw(AssertionError("legacy main gate was called")),
    )

    with pytest.raises(HTTPException) as exc:
        support_broadcast_routes._platform_actor("Bearer forged-legacy-token")
    assert exc.value.status_code == 403

    _bind_context(monkeypatch, auth_engine, "ip-owner")
    actor = support_broadcast_routes._platform_actor(None)
    assert actor["user_id"] == "ip-owner"
