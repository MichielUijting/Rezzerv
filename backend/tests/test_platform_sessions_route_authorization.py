from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import platform_sessions_routes
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext, ensure_server_session_schema


SESSIONS_PERMISSION = "platform.sessions.revoke"


@pytest.fixture
def auth_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        ensure_server_session_schema(conn)
        conn.execute(text("""
            CREATE TABLE app_users (
                id VARCHAR(64) PRIMARY KEY,
                email VARCHAR(255) NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email)
            VALUES
              ('platform-admin', 'platform-admin@example.test'),
              ('target-user', 'target-user@example.test')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('platform-admin', 'platform.platform_admin', 1),
              ('ip-owner', 'platform.ip_owner', 1),
              ('superuser', 'platform.superuser', 1),
              ('support-reader', 'platform.support_read', 1),
              ('frontteam', 'platform.frontteam', 1)
        """))
        sessions = [
            {
                "id": "session-platform-admin",
                "hash": "a" * 64,
                "user_id": "platform-admin",
                "household_id": None,
                "issued_at": now - timedelta(minutes=20),
                "expires_at": now + timedelta(hours=2),
                "revoked_at": None,
            },
            {
                "id": "session-target-active",
                "hash": "b" * 64,
                "user_id": "target-user",
                "household_id": "household-private",
                "issued_at": now - timedelta(minutes=10),
                "expires_at": now + timedelta(hours=3),
                "revoked_at": None,
            },
            {
                "id": "session-target-revoked",
                "hash": "c" * 64,
                "user_id": "target-user",
                "household_id": "0",
                "issued_at": now - timedelta(hours=2),
                "expires_at": now + timedelta(hours=1),
                "revoked_at": now - timedelta(minutes=5),
            },
            {
                "id": "session-target-expired",
                "hash": "d" * 64,
                "user_id": "target-user",
                "household_id": None,
                "issued_at": now - timedelta(hours=4),
                "expires_at": now - timedelta(hours=1),
                "revoked_at": None,
            },
        ]
        for item in sessions:
            conn.execute(text("""
                INSERT INTO server_sessions(
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at, session_version, revoked_at
                )
                VALUES(
                    :id, :hash, :user_id, :household_id,
                    :issued_at, :expires_at, 1, :revoked_at
                )
            """), item)
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
    monkeypatch.setattr(platform_sessions_routes, "engine", auth_engine)
    return context


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("platform-admin", True),
        ("ip-owner", True),
        ("superuser", False),
        ("support-reader", False),
        ("frontteam", False),
        ("ordinary-admin", False),
    ],
)
def test_session_routes_use_exact_canonical_permission_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        payload = platform_sessions_routes.get_platform_sessions()
        assert payload["count"] == 2
        return

    with pytest.raises(HTTPException) as exc:
        platform_sessions_routes.get_platform_sessions()
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {SESSIONS_PERMISSION}"


def test_platform_admin_lists_only_active_sessions_with_safe_projection(
    monkeypatch,
    auth_engine,
):
    context = _bind_context(monkeypatch, auth_engine, "platform-admin")

    payload = platform_sessions_routes.get_platform_sessions()

    assert context.context_type == "none"
    assert context.active_household_id is None
    assert payload["household_context_used"] is False
    assert payload["context_type"] == "none"
    assert payload["count"] == 2
    assert {item["session_id"] for item in payload["items"]} == {
        "session-platform-admin",
        "session-target-active",
    }
    for item in payload["items"]:
        assert set(item) == {
            "session_id",
            "user_id",
            "email",
            "issued_at",
            "expires_at",
            "is_current",
        }
        serialized = repr(item)
        assert "session_token_hash" not in serialized
        assert "household-private" not in serialized
        assert "active_household_id" not in serialized
        assert "replaced_by_session_id" not in serialized

    current = next(item for item in payload["items"] if item["is_current"])
    assert current["session_id"] == "session-platform-admin"


def test_platform_admin_revokes_target_by_internal_id_without_touching_current_session(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    payload = platform_sessions_routes.revoke_platform_session(
        "session-target-active"
    )

    assert payload["household_context_used"] is False
    assert payload["context_type"] == "none"
    assert payload["item"]["session_id"] == "session-target-active"
    assert payload["item"]["user_id"] == "target-user"
    assert payload["item"]["revoked_at"]

    with auth_engine.connect() as conn:
        rows = {
            row["id"]: row["revoked_at"]
            for row in conn.execute(text("""
                SELECT id, revoked_at
                FROM server_sessions
                WHERE id IN ('session-platform-admin', 'session-target-active')
            """)).mappings()
        }
    assert rows["session-target-active"] is not None
    assert rows["session-platform-admin"] is None

    reread = platform_sessions_routes.get_platform_sessions()
    assert reread["count"] == 1
    assert reread["items"][0]["session_id"] == "session-platform-admin"


def test_current_management_session_cannot_be_revoked_from_platform_page(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    with pytest.raises(HTTPException) as exc:
        platform_sessions_routes.revoke_platform_session(
            "session-platform-admin"
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "De huidige beheersessie kan hier niet worden ingetrokken; gebruik Uitloggen."
    )
    with auth_engine.connect() as conn:
        revoked_at = conn.execute(text("""
            SELECT revoked_at FROM server_sessions
            WHERE id = 'session-platform-admin'
        """)).scalar_one()
    assert revoked_at is None


def test_unknown_or_inactive_target_is_rejected_without_mutating_other_sessions(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    with pytest.raises(HTTPException) as missing:
        platform_sessions_routes.revoke_platform_session("missing-session")
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as revoked:
        platform_sessions_routes.revoke_platform_session("session-target-revoked")
    assert revoked.value.status_code == 409
    assert revoked.value.detail == "Sessie is al ingetrokken"

    with pytest.raises(HTTPException) as expired:
        platform_sessions_routes.revoke_platform_session("session-target-expired")
    assert expired.value.status_code == 409
    assert expired.value.detail == "Sessie is al verlopen"


def test_platform_admin_role_revocation_blocks_next_session_management_request(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    assert platform_sessions_routes.get_platform_sessions()["count"] == 2

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        platform_sessions_routes.get_platform_sessions()
    assert exc.value.status_code == 403


def test_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(platform_sessions_routes, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        invalid_session,
    )

    with pytest.raises(HTTPException) as exc:
        platform_sessions_routes.get_platform_sessions()
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"
