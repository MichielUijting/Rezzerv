from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.fixture_lifecycle_route_authorization import (
    FIXTURE_LIFECYCLE_PERMISSION,
    FIXTURE_LIFECYCLE_ROUTES,
    required_fixture_lifecycle_permission,
)
from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.receipt_export_fixture_route_authorization import (
    RECEIPT_EXPORT_FIXTURE_ROUTES,
)
from app.services.server_session_service import ServerSessionContext
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


PERMISSION = "platform.test_fixtures.manage"
MIGRATED_ROUTES = frozenset(
    {
        ("POST", "/api/testing/diagnostics/store-location-options"),
        ("POST", "/api/testing/fixtures/browser-regression/reset"),
        ("POST", "/api/testing/fixtures/cleanup"),
        ("POST", "/api/testing/fixtures/inventory/ensure"),
        ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
        ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    }
)
HYBRID_CUTOVER_ROUTES = frozenset(
    {
        ("POST", "/api/testing/regression/almost-out-prediction"),
        ("POST", "/api/testing/regression/almost-out-self-test"),
    }
)
LEGACY_LOCAL_GUARD_ROUTES = frozenset(
    {
        ("POST", "/api/testing/fixtures/browser-regression/reset"),
        ("POST", "/api/testing/fixtures/cleanup"),
        ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
        ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    }
)
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
    email = SUPERGEBRUIKER_EMAIL if user_id == "superuser" else f"{user_id}@example.test"
    return ServerSessionContext(
        session_id=f"session-{user_id}",
        user_id=user_id,
        email=email,
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


def test_fixture_lifecycle_classifier_is_exact_and_reuses_existing_permission():
    assert FIXTURE_LIFECYCLE_PERMISSION == PERMISSION
    assert FIXTURE_LIFECYCLE_ROUTES == MIGRATED_ROUTES
    assert FIXTURE_LIFECYCLE_ROUTES.isdisjoint(RECEIPT_EXPORT_FIXTURE_ROUTES)
    for method, path in MIGRATED_ROUTES:
        assert required_fixture_lifecycle_permission(method, path) == PERMISSION
        assert required_fixture_lifecycle_permission(method.lower(), path) == PERMISSION
    for method, path in HYBRID_CUTOVER_ROUTES:
        assert required_fixture_lifecycle_permission(method, path) is None


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
def test_fixture_lifecycle_permission_uses_canonical_role_matrix(
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


def test_request_scoped_legacy_guard_bridge_allows_platform_admin_only_while_grant_is_bound(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_admin_from_session(
            "Bearer forged-legacy-token"
        )
    assert exc.value.status_code == 403

    token = session_request_context.bind_canonical_platform_permission_grant(PERMISSION)
    try:
        user = session_request_context.require_platform_admin_from_session(
            "Bearer forged-legacy-token"
        )
        assert user["user_id"] == "platform-admin"
    finally:
        session_request_context.reset_canonical_platform_permission_grant(token)

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_admin_from_session(None)
    assert exc.value.status_code == 403


def test_bound_fixture_grant_does_not_restore_current_superuser_access(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "superuser")
    token = session_request_context.bind_canonical_platform_permission_grant(PERMISSION)
    try:
        with pytest.raises(HTTPException) as exc:
            session_request_context.require_platform_admin_from_session(None)
        assert exc.value.status_code == 403
        assert exc.value.detail == f"Ontbrekende platformpermissie: {PERMISSION}"
    finally:
        session_request_context.reset_canonical_platform_permission_grant(token)


def test_bound_fixture_grant_rechecks_revocation_before_legacy_handler_work(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    token = session_request_context.bind_canonical_platform_permission_grant(PERMISSION)
    try:
        assert (
            session_request_context.require_platform_admin_from_session(None)["user_id"]
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
            session_request_context.require_platform_admin_from_session(None)
        assert exc.value.status_code == 403
    finally:
        session_request_context.reset_canonical_platform_permission_grant(token)


def test_fixture_lifecycle_and_hybrid_routes_are_out_of_legacy_superuser_middleware():
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_ROUTES)
    assert PROTECTED_MUTATIONS.isdisjoint(HYBRID_CUTOVER_ROUTES)


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


def _calls_legacy_platform_admin(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == "require_platform_admin_user"
        for item in ast.walk(node)
    )


def test_all_six_runtime_routes_exist_and_legacy_local_calls_are_documented():
    routes = _route_nodes()
    for route in MIGRATED_ROUTES:
        assert route in routes
        assert _calls_legacy_platform_admin(routes[route]) is (route in LEGACY_LOCAL_GUARD_ROUTES)


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
    return sorted(
        item.lineno
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == call_name
    )


def test_session_middleware_checks_permission_binds_bridge_then_dispatches_and_resets():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_session = _call_lines(node, "bind_request_session")
    classify = _call_lines(node, "required_fixture_lifecycle_permission")
    require_permission = _call_lines(node, "require_platform_permission_from_session")
    bind_grant = _call_lines(node, "bind_canonical_platform_permission_grant")
    dispatch = _call_lines(node, "call_next")
    reset_grant = _call_lines(node, "reset_canonical_platform_permission_grant")
    reset_session = _call_lines(node, "reset_request_session")

    assert len(bind_session) == 1
    assert len(classify) == 1
    assert len(require_permission) >= 1
    assert len(bind_grant) == 1
    assert len(dispatch) == 1
    assert len(reset_grant) == 1
    assert len(reset_session) == 1
    assert bind_session[0] < classify[0] < require_permission[0] < bind_grant[0] < dispatch[0]
    assert dispatch[0] < reset_grant[0] < reset_session[0]
