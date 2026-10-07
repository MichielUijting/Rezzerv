from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import session_request_context
from app.services.authorization_foundation_service import PLATFORM_ADMIN_PERMISSIONS
from app.services.household_reset_service import PRESERVED_TABLES
from app.services.server_session_service import ServerSessionContext
from app.testing.postgresql_platform_authorization_fixture import (
    cleanup_platform_authorization_test_engine,
    create_platform_authorization_test_engine,
)


PERMISSION = "platform.recovery.manage"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = BACKEND_ROOT / "app" / "api" / "platform_household_reset_routes.py"
SERVICE_SOURCE = BACKEND_ROOT / "app" / "services" / "household_reset_service.py"
FRONTEND_SOURCE = BACKEND_ROOT.parent / "frontend" / "src" / "features" / "platform" / "PlatformRecoveryPage.jsx"


@pytest.fixture
def auth_engine():
    engine = create_platform_authorization_test_engine()
    try:
        yield engine
    finally:
        cleanup_platform_authorization_test_engine(engine)


def _context(user_id: str) -> ServerSessionContext:
    now = datetime.now(timezone.utc)
    if user_id == "superuser":
        context_type = "system"
        household_id = "0"
        role = "owner"
    elif user_id in {"platform-admin", "ip-owner"}:
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
        is_platform_admin=user_id == "platform-admin",
        is_ip_owner=user_id == "ip-owner",
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


def test_household_reset_reuses_platform_recovery_permission_only():
    assert PERMISSION in PLATFORM_ADMIN_PERMISSIONS
    assert "platform.household_reset.manage" not in PLATFORM_ADMIN_PERMISSIONS

    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    assert 'PLATFORM_HOUSEHOLD_RESET_PERMISSION = "platform.recovery.manage"' in route_source
    assert 'require_platform_permission_from_session(' in route_source
    assert '@router.post("/api/platform/recovery/reset-household")' in route_source


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("platform-admin", True),
        ("superuser", False),
        ("ip-owner", False),
        ("ordinary-admin", False),
        ("ordinary-member", False),
    ],
)
def test_only_platform_admin_role_has_reset_authority(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    context = _bind_context(monkeypatch, auth_engine, user_id)
    if allowed:
        actual = session_request_context.require_platform_permission_from_session(PERMISSION)
        assert actual is context
        assert actual.context_type == "none"
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(PERMISSION)
    assert exc.value.status_code == 403


def test_reset_service_preserves_identity_shell_and_audit():
    required = {
        "household_registry",
        "household_memberships",
        "auth_membership_roles",
        "auth_audit_log",
        "app_users",
        "server_sessions",
    }
    assert required.issubset(PRESERVED_TABLES)

    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert 'expected_confirmation = f"RESET {target}"' in source
    assert 'target in FORBIDDEN_HOUSEHOLD_IDS' in source
    assert 'context_type == "system"' in source
    assert "_membership_snapshot" in source
    assert "Lidmaatschappen veranderden onverwacht" in source
    assert "_revoke_household_sessions" in source
    assert "Resetcontrole vond resterende huishouddata" in source
    assert "with engine.begin()" not in source


def test_route_audits_reset_without_exposing_household_content():
    source = ROUTE_SOURCE.read_text(encoding="utf-8")
    assert 'action="platform.household.reset"' in source
    assert 'actor_type="platform_admin"' in source
    assert '"deleted_row_count": result["deleted_row_count"]' in source
    assert '"deleted_tables": sorted(result["deleted_by_table"])' in source
    assert "household_context_used" in source
    assert '"context_type": context.context_type' in source
    assert "password" not in source.lower()


def test_recovery_ui_requires_destructive_confirmation_phrase():
    source = FRONTEND_SOURCE.read_text(encoding="utf-8")
    assert "Huishouden volledig resetten" in source
    assert "RESET ${resetConfirmationTarget}" in source
    assert "/api/platform/recovery/reset-household" in source
    assert "wachtwoord-/inloggegevens" in source
    assert "Systeemhuishouden 0 is uitgesloten" in source
    assert "platform-reset-household-confirmation" in source
