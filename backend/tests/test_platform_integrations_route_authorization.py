from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import platform_integrations_routes
from app.services import email_config_service, session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.testing.authorization_schema_fixture import install_authorization_schema


INTEGRATIONS_PERMISSION = "platform.integrations.manage"


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
              ('platform-admin', 'platform.platform_admin', 1),
              ('ip-owner', 'platform.ip_owner', 1),
              ('superuser', 'platform.superuser', 1),
              ('support-reader', 'platform.support_read', 1),
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


def _bind_safe_integration_status(monkeypatch):
    registry = SimpleNamespace(
        active_provider_code="rezzerv-legacy",
        available_provider_codes=lambda: ("rezzerv-legacy",),
    )
    monkeypatch.setattr(
        platform_integrations_routes.receipt_scanner_runtime,
        "get_receipt_scanner_gateway",
        lambda: SimpleNamespace(registry=registry),
    )
    monkeypatch.setattr(email_config_service, "REZZERV_EMAIL_ENABLED", True)
    monkeypatch.setattr(email_config_service, "RESEND_API_KEY", "SECRET-RESEND-KEY")
    monkeypatch.setattr(
        email_config_service,
        "REZZERV_NOTIFICATION_FROM_EMAIL",
        "private-sender@example.test",
    )


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
def test_platform_integrations_route_uses_exact_canonical_permission_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    _bind_context(monkeypatch, auth_engine, user_id)
    _bind_safe_integration_status(monkeypatch)

    if allowed:
        payload = platform_integrations_routes.get_platform_integrations()
        assert payload["count"] == 2
        return

    with pytest.raises(HTTPException) as exc:
        platform_integrations_routes.get_platform_integrations()
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {INTEGRATIONS_PERMISSION}"


def test_platform_integrations_projection_is_read_only_household_free_and_secret_free(
    monkeypatch,
    auth_engine,
):
    context = _bind_context(monkeypatch, auth_engine, "platform-admin")
    _bind_safe_integration_status(monkeypatch)

    payload = platform_integrations_routes.get_platform_integrations()

    assert context.context_type == "none"
    assert context.active_household_id is None
    assert payload["read_only"] is True
    assert payload["household_context_used"] is False
    assert [item["key"] for item in payload["items"]] == [
        "receipt-scanner",
        "outbound-email",
    ]

    scanner = payload["items"][0]
    assert scanner == {
        "key": "receipt-scanner",
        "label": "Kassabonscanner",
        "scope": "platform",
        "provider": "rezzerv-legacy",
        "status": "ready",
        "contract_version": "1.0",
        "available_providers": ["rezzerv-legacy"],
    }

    email = payload["items"][1]
    assert email == {
        "key": "outbound-email",
        "label": "Uitgaande e-mail",
        "scope": "platform",
        "provider": "resend",
        "status": "ready",
        "delivery_enabled": True,
        "api_key_configured": True,
        "sender_configured": True,
    }

    serialized = str(payload)
    assert "SECRET-RESEND-KEY" not in serialized
    assert "private-sender@example.test" not in serialized
    assert "household-1" not in serialized
    assert "household_id" not in serialized


def test_invalid_receipt_scanner_configuration_is_reported_without_raw_error(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    monkeypatch.setattr(
        platform_integrations_routes.receipt_scanner_runtime,
        "get_receipt_scanner_gateway",
        lambda: (_ for _ in ()).throw(
            platform_integrations_routes.ProviderConfigurationError(
                "SECRET-SCANNER-CONFIG"
            )
        ),
    )
    monkeypatch.setattr(email_config_service, "REZZERV_EMAIL_ENABLED", False)
    monkeypatch.setattr(email_config_service, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_config_service, "REZZERV_NOTIFICATION_FROM_EMAIL", "")

    payload = platform_integrations_routes.get_platform_integrations()

    scanner = payload["items"][0]
    assert scanner["status"] == "configuration_error"
    assert scanner["provider"] is None
    assert "SECRET-SCANNER-CONFIG" not in str(payload)


def test_platform_admin_revocation_blocks_next_integrations_read(monkeypatch, auth_engine):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    _bind_safe_integration_status(monkeypatch)

    assert platform_integrations_routes.get_platform_integrations()["count"] == 2

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        platform_integrations_routes.get_platform_integrations()
    assert exc.value.status_code == 403


def test_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(session_request_context, "resolve_current_server_session", invalid_session)

    with pytest.raises(HTTPException) as exc:
        platform_integrations_routes.get_platform_integrations()
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"
