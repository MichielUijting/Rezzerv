from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import platform_audit_routes
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.testing.authorization_schema_fixture import install_authorization_schema


AUDIT_PERMISSION = "platform.audit.view"


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
        conn.execute(text("""
            INSERT INTO auth_audit_log(
                id, actor_user_id, actor_type, household_id, support_session_id,
                action, object_type, object_id, old_value, new_value, reason,
                ticket_reference, created_at
            ) VALUES
              (
                'audit-new', 'actor-new', 'platform', NULL, 'support-secret',
                'permission_changed', 'platform_role', 'platform.platform_admin',
                'SECRET-OLD', 'SECRET-NEW', 'SECRET-REASON', 'SECRET-TICKET',
                '2026-08-24T12:00:00+00:00'
              ),
              (
                'audit-old', 'actor-old', 'household', 'household-1', NULL,
                'role_changed', 'membership', 'member-1',
                NULL, NULL, NULL, NULL,
                '2026-08-23T12:00:00+00:00'
              )
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
    monkeypatch.setattr(platform_audit_routes, "engine", auth_engine)
    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        lambda: context,
    )
    return context


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("platform-admin", True),
        ("ip-owner", True),
        ("superuser", False),
        ("support-reader", True),
        ("frontteam", False),
        ("ordinary-admin", False),
    ],
)
def test_platform_audit_route_uses_canonical_permission_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        payload = platform_audit_routes.get_platform_authorization_audit(limit=20)
        assert payload["count"] == 2
        return

    with pytest.raises(HTTPException) as exc:
        platform_audit_routes.get_platform_authorization_audit(limit=20)
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {AUDIT_PERMISSION}"


def test_platform_audit_projection_is_read_only_ordered_and_excludes_sensitive_payloads(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    payload = platform_audit_routes.get_platform_authorization_audit(limit=20)

    assert payload["limit"] == 20
    assert [item["id"] for item in payload["items"]] == ["audit-new", "audit-old"]
    assert set(payload["items"][0]) == {
        "id",
        "actor_user_id",
        "actor_type",
        "household_id",
        "action",
        "object_type",
        "object_id",
        "created_at",
    }
    serialized = str(payload)
    for secret in (
        "SECRET-OLD",
        "SECRET-NEW",
        "SECRET-REASON",
        "SECRET-TICKET",
        "support-secret",
    ):
        assert secret not in serialized


def test_platform_admin_revocation_blocks_next_audit_read(monkeypatch, auth_engine):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    assert platform_audit_routes.get_platform_authorization_audit(limit=1)["count"] == 1

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        platform_audit_routes.get_platform_authorization_audit(limit=1)
    assert exc.value.status_code == 403


def test_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(platform_audit_routes, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(session_request_context, "resolve_current_server_session", invalid_session)

    with pytest.raises(HTTPException) as exc:
        platform_audit_routes.get_platform_authorization_audit(limit=20)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"
