from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.kassa_diagnostic_route_authorization import (
    KASSA_BACKGROUND_JOB_PERMISSION,
    KASSA_DIAGNOSTIC_ROUTE_PERMISSIONS,
    KASSA_DIAGNOSTICS_VIEW_PERMISSION,
    KASSA_RUN_ROUTES,
    KASSA_STATUS_ROUTES,
    required_kassa_diagnostic_permission,
)
from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.server_session_service import ServerSessionContext


BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
DIAGNOSTICS_VIEW_PERMISSION = "platform.diagnostics.view"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"
REGRESSION_ROUTE_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "routes" / "kassa_regression_routes.py"
SMOKE_ROUTE_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "routes" / "kassa_smoke_routes.py"

EXPECTED_RUN_ROUTES = frozenset(
    {
        ("POST", "/api/admin/kassa-regression/run"),
        ("POST", "/api/admin/kassa-smoke/run"),
    }
)
EXPECTED_STATUS_ROUTES = frozenset(
    {
        ("GET", "/api/admin/kassa-regression/status"),
        ("GET", "/api/admin/kassa-smoke/status"),
    }
)


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


def test_kassa_classifier_is_exact_and_reuses_existing_permissions():
    assert KASSA_BACKGROUND_JOB_PERMISSION == BACKGROUND_JOB_PERMISSION
    assert KASSA_DIAGNOSTICS_VIEW_PERMISSION == DIAGNOSTICS_VIEW_PERMISSION
    assert KASSA_RUN_ROUTES == EXPECTED_RUN_ROUTES
    assert KASSA_STATUS_ROUTES == EXPECTED_STATUS_ROUTES
    assert set(KASSA_DIAGNOSTIC_ROUTE_PERMISSIONS) == (
        EXPECTED_RUN_ROUTES | EXPECTED_STATUS_ROUTES
    )

    for method, path in EXPECTED_RUN_ROUTES:
        assert required_kassa_diagnostic_permission(method, path) == BACKGROUND_JOB_PERMISSION
        assert required_kassa_diagnostic_permission(method.lower(), path) == BACKGROUND_JOB_PERMISSION

    for method, path in EXPECTED_STATUS_ROUTES:
        assert required_kassa_diagnostic_permission(method, path) == DIAGNOSTICS_VIEW_PERMISSION
        assert required_kassa_diagnostic_permission(method.lower(), path) == DIAGNOSTICS_VIEW_PERMISSION

    assert required_kassa_diagnostic_permission("GET", "/api/admin/kassa-regression/run") is None
    assert required_kassa_diagnostic_permission("POST", "/api/admin/kassa-smoke/status") is None
    assert required_kassa_diagnostic_permission("POST", "/api/testing/regression/all/run") is None


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
def test_kassa_permissions_use_canonical_platform_role_matrix(
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
def test_invalid_server_session_remains_401_despite_forged_bearer(
    monkeypatch,
    auth_engine,
    permission,
):
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
def test_platform_admin_revocation_is_effective_on_next_kassa_permission_check(
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


def test_kassa_run_routes_are_removed_from_legacy_superuser_guard():
    assert PROTECTED_MUTATIONS.isdisjoint(EXPECTED_RUN_ROUTES)
    assert PROTECTED_MUTATIONS.isdisjoint(EXPECTED_STATUS_ROUTES)


def _route_nodes(path: Path) -> dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
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


def test_all_four_runtime_kassa_entrypoints_exist_without_local_legacy_admin_guard():
    routes = {
        **_route_nodes(REGRESSION_ROUTE_SOURCE_PATH),
        **_route_nodes(SMOKE_ROUTE_SOURCE_PATH),
    }
    for route in EXPECTED_RUN_ROUTES | EXPECTED_STATUS_ROUTES:
        assert route in routes
        legacy_calls = [
            item
            for item in ast.walk(routes[route])
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "require_platform_admin_user"
        ]
        assert not legacy_calls


def test_session_middleware_checks_kassa_permission_before_dispatch():
    source = SESSION_ENTRYPOINT_SOURCE_PATH.read_text(encoding="utf-8")
    bind_session = source.index("token = bind_request_session(request)")
    classify = source.index("required_kassa_diagnostic_permission(")
    require_permission = source.index("require_platform_permission_from_session(", classify)
    dispatch = source.index("return await call_next(request)")

    assert bind_session < classify < require_permission < dispatch
    assert "kassa_permission" in source[classify:dispatch]
