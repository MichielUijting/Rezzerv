from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import (
    PLATFORM_ADMIN_PERMISSIONS,
    V2_PLATFORM_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.server_session_service import ServerSessionContext
from app.services.testing_status_route_authorization import (
    TESTING_STATUS_PERMISSION,
    TESTING_STATUS_ROUTES,
    required_testing_status_permission,
)


PERMISSION = "platform.diagnostics.view"
ROUTE = ("GET", "/api/testing/status")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"


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
        if user_id == "ordinary-owner":
            role = "owner"
        elif user_id == "ordinary-admin":
            role = "admin"
        else:
            role = "member"
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


def test_testing_status_classifier_is_exact_and_reuses_diagnostics_permission():
    assert TESTING_STATUS_PERMISSION == PERMISSION
    assert TESTING_STATUS_ROUTES == frozenset({ROUTE})
    assert PERMISSION in V2_PLATFORM_PERMISSIONS
    assert PERMISSION in PLATFORM_ADMIN_PERMISSIONS
    assert required_testing_status_permission("GET", ROUTE[1]) == PERMISSION
    assert required_testing_status_permission("get", ROUTE[1]) == PERMISSION
    assert required_testing_status_permission("POST", ROUTE[1]) is None
    assert required_testing_status_permission("GET", "/api/testing/reports/latest") is None


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("ip-owner", True),
        ("platform-admin", True),
        ("superuser", False),
        ("support-reader", False),
        ("frontteam", False),
        ("ordinary-admin", False),
        ("ordinary-owner", False),
    ],
)
def test_testing_status_uses_approved_canonical_role_matrix(
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
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {PERMISSION}"


def test_missing_or_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        invalid_session,
    )
    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_admin_revocation_applies_on_next_status_permission_check(
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


def _route_nodes() -> dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(MAIN_SOURCE_PATH.read_text(encoding="utf-8"))
    routes: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                routes[(method, str(decorator.args[0].value))] = node
    return routes


def _named_calls(node: ast.AST, function_name: str) -> list[ast.Call]:
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == function_name
    ]


def test_testing_status_handler_no_longer_calls_legacy_platform_admin_guard():
    routes = _route_nodes()
    node = routes[ROUTE]
    assert _named_calls(node, "require_platform_admin_user") == []


def _function_node(path: Path, function_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    assert len(matches) == 1
    return matches[0]


def _call_lines(node: ast.AST, call_name: str) -> list[int]:
    return sorted(call.lineno for call in _named_calls(node, call_name))


def test_status_permission_check_runs_after_session_bind_and_before_dispatch():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_lines = _call_lines(node, "bind_request_session")
    classify_lines = _call_lines(node, "required_testing_status_permission")
    permission_lines = _call_lines(node, "require_platform_permission_from_session")
    dispatch_lines = _call_lines(node, "call_next")

    assert len(bind_lines) == 1
    assert len(classify_lines) == 1
    assert permission_lines
    assert len(dispatch_lines) == 1
    assert bind_lines[0] < classify_lines[0] < dispatch_lines[0]
    assert any(classify_lines[0] < line < dispatch_lines[0] for line in permission_lines)
