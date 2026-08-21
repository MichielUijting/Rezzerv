from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import app.main as legacy_main
from app.services import session_request_context as request_context
from app.services.server_session_service import ServerSessionContext


def _context(
    *,
    household_id: str | None = "household-1",
    role: str | None = "member",
    context_type: str = "regular",
):
    now = datetime.now(timezone.utc)
    return ServerSessionContext(
        session_id="record-1",
        user_id="user-1",
        email="member@example.test",
        active_household_id=household_id,
        context_type=context_type,
        role=role,
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_legacy_authorization_value_is_ignored_without_cookie_context(monkeypatch):
    def fail_closed():
        raise HTTPException(status_code=401, detail="Geen geldige sessie")

    monkeypatch.setattr(request_context, "resolve_current_server_session", fail_closed)

    with pytest.raises(HTTPException) as exc:
        request_context.legacy_user_payload_from_session("Bearer rezzerv-dev-token")

    assert exc.value.status_code == 401


def test_legacy_user_payload_comes_only_from_server_session(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(role="admin"),
    )

    payload = request_context.legacy_user_payload_from_session(
        "Bearer rezzerv-dev-token::other-user@example.test"
    )

    assert payload == {
        "id": "user-1",
        "user_id": "user-1",
        "email": "member@example.test",
        "role": "admin",
        "household_id": "household-1",
        "active_household_id": "household-1",
    }


@pytest.mark.parametrize(
    ("household_id", "context_type", "requested_household_id"),
    [
        ("household-1", "regular", "household-2"),
        ("0", "system", "household-1"),
    ],
)
def test_requested_household_must_equal_active_server_household(
    monkeypatch,
    household_id,
    context_type,
    requested_household_id,
):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id=household_id, context_type=context_type),
    )

    with pytest.raises(HTTPException) as exc:
        request_context.household_context_from_session(
            "Bearer ignored",
            requested_household_id=requested_household_id,
        )

    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("household_id", "context_type"),
    [("household-1", "regular"), ("0", "system")],
)
def test_matching_household_context_is_returned(
    monkeypatch,
    household_id,
    context_type,
):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(
            household_id=household_id,
            role="member",
            context_type=context_type,
        ),
    )

    payload = request_context.household_context_from_session(
        requested_household_id=household_id
    )

    assert payload["active_household_id"] == household_id
    assert payload["user_id"] == "user-1"
    assert payload["role"] == "member"
    assert payload["display_role"] == "lid"


def test_none_session_is_rejected_by_household_context_bridge(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id=None, role=None, context_type="none"),
    )

    with pytest.raises(HTTPException) as exc:
        request_context.household_context_from_session()

    assert exc.value.status_code == 403
    assert exc.value.detail == "Geen actieve huishoudcontext beschikbaar"


def test_fallback_arguments_cannot_override_server_household(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id="household-1", context_type="regular"),
    )

    assert request_context.authorized_household_id_from_session(
        fallback="demo-household",
    ) == "household-1"
    assert request_context.request_household_id_from_session(
        fallback="demo-household",
    ) == "household-1"


def test_legacy_household_endpoint_cannot_reconstruct_membership_for_none_session(
    monkeypatch,
):
    import app.session_entrypoint  # noqa: F401

    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id=None, role=None, context_type="none"),
    )
    monkeypatch.setattr(
        legacy_main,
        "get_current_user_from_authorization",
        lambda _authorization=None: {
            "id": "user-1",
            "user_id": "user-1",
            "email": "platform@example.test",
            "role": None,
            "household_id": None,
            "active_household_id": None,
            "memberships": [{"household_id": "household-1", "role": "member"}],
        },
    )

    with pytest.raises(HTTPException) as exc:
        legacy_main.get_household()

    assert exc.value.status_code == 403
    assert exc.value.detail == "Geen actieve huishoudcontext beschikbaar"


def test_legacy_household_wrapper_uses_regular_server_session_not_user_membership(
    monkeypatch,
):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                created_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry (id, naam, created_at)
            VALUES
              ('household-1', 'Huishouden A', '2026-08-21 12:00:00'),
              ('household-2', 'Huishouden B', '2026-08-21 12:00:00')
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                user_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_memberships (user_id, household_id, role)
            VALUES ('user-1', 'household-2', 'owner')
        """))

    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id="household-1", role="member"),
    )
    monkeypatch.setattr(request_context, "engine", engine)
    monkeypatch.setattr(legacy_main, "engine", engine)
    monkeypatch.setattr(
        legacy_main,
        "build_capabilities_payload",
        lambda _conn, _context: {
            "permissions": {},
            "member_permission_policies": {},
            "supported_permissions": [],
            "can_manage_member_permissions": False,
        },
    )
    monkeypatch.setattr(
        legacy_main,
        "get_household_store_import_simplification_level",
        lambda _conn, _household_id: "default",
    )

    import app.session_entrypoint as session_entrypoint

    session_entrypoint.activate_server_side_route_context()
    payload = legacy_main.get_household()

    assert payload["active_household_id"] == "household-1"
    assert payload["active_household_name"] == "Huishouden A"
    assert payload["role"] == "member"
    assert payload["membership_count"] == 1
    assert payload["can_switch_households"] is False
    assert len(payload["memberships"]) == 1
    assert payload["memberships"][0]["household_id"] == "household-1"
    assert "household-2" not in str(payload)
    assert not any("household_memberships" in statement for statement in statements)


@pytest.mark.parametrize(
    ("canonical_role", "expected_display_role"),
    [
        ("owner", "admin"),
        ("admin", "admin"),
        ("member", "lid"),
        ("advanced_member", "lid"),
        ("viewer", "viewer"),
        ("household.owner", "admin"),
        ("household.admin", "admin"),
        ("household.member", "lid"),
        ("household.advanced_member", "lid"),
        ("household.viewer", "viewer"),
    ],
)
def test_canonical_role_is_translated_for_legacy_guards(
    monkeypatch,
    canonical_role,
    expected_display_role,
):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(role=canonical_role),
    )

    payload = request_context.household_context_from_session()

    assert payload["role"] == canonical_role
    assert payload["display_role"] == expected_display_role


def test_owner_session_passes_legacy_receipt_write_guard(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(role="owner"),
    )
    monkeypatch.setattr(
        legacy_main,
        "require_household_context",
        request_context.household_context_from_session,
    )

    conn = Mock()
    conn.execute.return_value.mappings.return_value.first.return_value = {
        "household_id": "household-1"
    }

    context = legacy_main.require_receipt_write_context(conn, "receipt-1", None)

    assert context["role"] == "owner"
    assert context["display_role"] == "admin"
    assert context["active_household_id"] == "household-1"


def test_viewer_session_remains_blocked_by_legacy_receipt_write_guard(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(role="viewer"),
    )
    monkeypatch.setattr(
        legacy_main,
        "require_household_context",
        request_context.household_context_from_session,
    )

    conn = Mock()
    conn.execute.return_value.mappings.return_value.first.return_value = {
        "household_id": "household-1"
    }

    with pytest.raises(HTTPException) as exc:
        legacy_main.require_receipt_write_context(conn, "receipt-1", None)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Alleen admin en lid mogen kassabonnen aanpassen"


def test_entrypoint_replaces_central_legacy_guards():
    import app.session_entrypoint  # noqa: F401

    assert legacy_main.get_current_user_from_authorization is request_context.legacy_user_payload_from_session
    assert legacy_main.resolve_household_context_for_user is request_context.legacy_household_context_from_session
    assert legacy_main.require_household_context is request_context.household_context_from_session
