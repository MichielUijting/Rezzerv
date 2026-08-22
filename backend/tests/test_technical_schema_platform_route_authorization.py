from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.server_session_service import ServerSessionContext


PERMISSION = "platform.technical_configuration.manage"
ROUTE_PATH = "/api/admin/inventory/groups/ensure-schema"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "product_inventory_group_routes.py"


@pytest.fixture
def auth_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
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
    ("user_id", "allowed"),
    [
        ("ip-owner", True),
        ("platform-admin", True),
        ("superuser", False),
        ("support-reader", False),
        ("frontteam", False),
        ("ordinary-admin", False),
    ],
)
def test_technical_schema_permission_uses_registered_platform_role_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        actual_context = session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer forged-legacy-token",
        )
        assert actual_context is expected_context
        assert actual_context.user_id == user_id
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {PERMISSION}"


def test_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        invalid_session,
    )

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(PERMISSION)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_admin_revocation_is_effective_on_next_permission_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    assert (
        session_request_context.require_platform_permission_from_session(PERMISSION).user_id
        == "platform-admin"
    )

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(PERMISSION)

    assert exc.value.status_code == 403


def _ensure_schema_route_node() -> ast.FunctionDef:
    tree = ast.parse(ROUTE_SOURCE_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "inventory_groups_ensure_schema":
            return node
    raise AssertionError("inventory_groups_ensure_schema route ontbreekt")


def test_ensure_schema_route_checks_canonical_permission_before_schema_mutation():
    node = _ensure_schema_route_node()
    argument_names = {arg.arg for arg in node.args.args}
    assert "authorization" in argument_names

    calls = [call for call in ast.walk(node) if isinstance(call, ast.Call)]
    permission_calls = [
        call
        for call in calls
        if isinstance(call.func, ast.Name)
        and call.func.id == "require_platform_permission_from_session"
    ]
    schema_calls = [
        call
        for call in calls
        if isinstance(call.func, ast.Name)
        and call.func.id == "ensure_product_inventory_group_schema"
    ]

    assert len(permission_calls) == 1
    assert len(schema_calls) == 1
    permission_call = permission_calls[0]
    assert permission_call.args
    assert isinstance(permission_call.args[0], ast.Constant)
    assert permission_call.args[0].value == PERMISSION
    assert permission_call.lineno < schema_calls[0].lineno


def test_ensure_schema_route_is_not_still_pre_gated_by_legacy_superuser_middleware():
    assert ("POST", ROUTE_PATH) not in PROTECTED_MUTATIONS
