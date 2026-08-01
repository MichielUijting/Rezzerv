from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.main as legacy_main
from app.services import session_request_context as request_context
from app.services.server_session_service import ServerSessionContext


def _context(*, household_id: str = "household-1", role: str = "member"):
    now = datetime.now(timezone.utc)
    return ServerSessionContext(
        session_id="record-1",
        user_id="user-1",
        email="member@example.test",
        active_household_id=household_id,
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


def test_requested_household_must_equal_active_server_household(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id="household-1"),
    )

    with pytest.raises(HTTPException) as exc:
        request_context.household_context_from_session(
            "Bearer ignored",
            requested_household_id="household-2",
        )

    assert exc.value.status_code == 403


def test_matching_household_context_is_returned(monkeypatch):
    monkeypatch.setattr(
        request_context,
        "resolve_current_server_session",
        lambda: _context(household_id="household-1", role="member"),
    )

    payload = request_context.household_context_from_session(
        requested_household_id="household-1"
    )

    assert payload["active_household_id"] == "household-1"
    assert payload["user_id"] == "user-1"
    assert payload["role"] == "member"


def test_entrypoint_replaces_central_legacy_guards():
    import app.session_entrypoint  # noqa: F401

    assert legacy_main.get_current_user_from_authorization is request_context.legacy_user_payload_from_session
    assert legacy_main.require_household_context is request_context.household_context_from_session
