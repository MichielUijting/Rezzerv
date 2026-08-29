from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.testing.authorization_schema_fixture import install_authorization_schema


BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
DIAGNOSTICS_VIEW_PERMISSION = "platform.diagnostics.view"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "dev_test_routes.py"

MIGRATED_POST_ROUTES = {
    "/api/testing/regression/smoke/run",
    "/api/testing/regression/all/run",
    "/api/testing/regression/layer1/run",
    "/api/testing/regression/layer2/run",
    "/api/testing/regression/layer3/run",
    "/api/testing/regression/parsing-fixtures/run",
    "/api/testing/regression/parsing-raw/run",
    "/api/testing/reports/complete",
}
LATEST_REPORT_ROUTE = "/api/testing/reports/latest"


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


@pytest.mark.parametrize(
    "permission",
    [BACKGROUND_JOB_PERMISSION, DIAGNOSTICS_VIEW_PERMISSION],
)
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
def test_test_orchestration_permissions_use_registered_platform_role_matrix(
    monkeypatch,
    auth_engine,
    permission,
    user_id,
    allowed,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        actual_context = session_request_context.require_platform_permission_from_session(
            permission,
            "Bearer forged-legacy-token",
        )
        assert actual_context is expected_context
        assert actual_context.user_id == user_id
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            permission,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {permission}"


@pytest.mark.parametrize(
    "permission",
    [BACKGROUND_JOB_PERMISSION, DIAGNOSTICS_VIEW_PERMISSION],
)
def test_invalid_server_session_remains_401(monkeypatch, auth_engine, permission):
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
            permission,
            "Bearer forged-legacy-token",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


@pytest.mark.parametrize(
    "permission",
    [BACKGROUND_JOB_PERMISSION, DIAGNOSTICS_VIEW_PERMISSION],
)
def test_platform_admin_revocation_is_effective_on_next_permission_check(
    monkeypatch,
    auth_engine,
    permission,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    assert (
        session_request_context.require_platform_permission_from_session(permission).user_id
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
        session_request_context.require_platform_permission_from_session(permission)

    assert exc.value.status_code == 403


def _route_tree() -> ast.Module:
    return ast.parse(ROUTE_SOURCE_PATH.read_text(encoding="utf-8"))


def _route_nodes() -> dict[tuple[str, str], ast.FunctionDef]:
    routes: dict[tuple[str, str], ast.FunctionDef] = {}
    for node in ast.walk(_route_tree()):
        if not isinstance(node, ast.FunctionDef):
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


def _assert_first_statement_is_permission_check(node: ast.FunctionDef, constant_name: str) -> None:
    assert any(arg.arg == "authorization" for arg in node.args.args)
    assert node.body, f"{node.name} heeft geen routebody"
    statement = node.body[0]
    assert isinstance(statement, ast.Expr)
    call = statement.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Name)
    assert call.func.id == "require_platform_permission_from_session"
    assert len(call.args) == 2
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == constant_name
    assert isinstance(call.args[1], ast.Name)
    assert call.args[1].id == "authorization"

    legacy_calls = [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == "require_platform_admin_user"
    ]
    assert not legacy_calls, f"{node.name} gebruikt nog de legacy platform-admin helper"


def test_route_permission_constants_match_canonical_permission_keys():
    assignments: dict[str, str] = {}
    for node in _route_tree().body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
            assignments[target.id] = str(node.value.value)

    assert assignments["BACKGROUND_JOB_PERMISSION"] == BACKGROUND_JOB_PERMISSION
    assert assignments["DIAGNOSTICS_VIEW_PERMISSION"] == DIAGNOSTICS_VIEW_PERMISSION


def test_migrated_post_routes_check_background_job_permission_before_work():
    routes = _route_nodes()
    assert MIGRATED_POST_ROUTES == {
        path for method, path in routes if method == "POST" and path in MIGRATED_POST_ROUTES
    }
    for path in MIGRATED_POST_ROUTES:
        _assert_first_statement_is_permission_check(
            routes[("POST", path)],
            "BACKGROUND_JOB_PERMISSION",
        )


def test_latest_report_route_checks_diagnostics_view_permission_before_read():
    routes = _route_nodes()
    _assert_first_statement_is_permission_check(
        routes[("GET", LATEST_REPORT_ROUTE)],
        "DIAGNOSTICS_VIEW_PERMISSION",
    )


def test_legacy_platform_admin_injection_is_never_called_by_migrated_router():
    router_functions = [
        node
        for node in _route_tree().body
        if isinstance(node, ast.FunctionDef) and node.name == "create_dev_test_router"
    ]
    assert len(router_functions) == 1
    legacy_calls = [
        item
        for item in ast.walk(router_functions[0])
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == "require_platform_admin_user"
    ]
    assert not legacy_calls
