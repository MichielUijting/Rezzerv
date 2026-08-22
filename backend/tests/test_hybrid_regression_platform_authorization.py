from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.fixture_lifecycle_route_authorization import FIXTURE_LIFECYCLE_ROUTES
from app.services.hybrid_regression_route_authorization import (
    HYBRID_REGRESSION_BACKGROUND_JOB_PERMISSION,
    HYBRID_REGRESSION_FIXTURE_PERMISSION,
    HYBRID_REGRESSION_REQUIRED_PERMISSIONS,
    HYBRID_REGRESSION_ROUTES,
    required_hybrid_regression_permissions,
)
from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.receipt_export_fixture_route_authorization import (
    RECEIPT_EXPORT_FIXTURE_ROUTES,
)
from app.services.server_session_service import ServerSessionContext
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
FIXTURE_PERMISSION = "platform.test_fixtures.manage"
MIGRATED_ROUTES = frozenset(
    {
        ("POST", "/api/testing/regression/almost-out-prediction"),
        ("POST", "/api/testing/regression/almost-out-self-test"),
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
            INSERT INTO auth_roles(role_key, scope, name, system_role, active)
            VALUES
              ('platform.job_only_test', 'platform', 'Job only test role', 0, 1),
              ('platform.fixture_only_test', 'platform', 'Fixture only test role', 0, 1)
        """))
        conn.execute(text("""
            INSERT INTO auth_role_permissions(role_key, permission_key)
            VALUES
              ('platform.job_only_test', 'platform.background_jobs.manage'),
              ('platform.fixture_only_test', 'platform.test_fixtures.manage')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('superuser', 'platform.superuser', 1),
              ('ip-owner', 'platform.ip_owner', 1),
              ('support-reader', 'platform.support_read', 1),
              ('platform-admin', 'platform.platform_admin', 1),
              ('frontteam', 'platform.frontteam', 1),
              ('job-only', 'platform.job_only_test', 1),
              ('fixture-only', 'platform.fixture_only_test', 1)
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
    elif user_id in {"platform-admin", "job-only", "fixture-only"}:
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


def test_hybrid_classifier_is_exact_and_requires_both_existing_permissions():
    assert HYBRID_REGRESSION_BACKGROUND_JOB_PERMISSION == BACKGROUND_JOB_PERMISSION
    assert HYBRID_REGRESSION_FIXTURE_PERMISSION == FIXTURE_PERMISSION
    assert HYBRID_REGRESSION_REQUIRED_PERMISSIONS == (
        BACKGROUND_JOB_PERMISSION,
        FIXTURE_PERMISSION,
    )
    assert HYBRID_REGRESSION_ROUTES == MIGRATED_ROUTES
    assert HYBRID_REGRESSION_ROUTES.isdisjoint(FIXTURE_LIFECYCLE_ROUTES)
    assert HYBRID_REGRESSION_ROUTES.isdisjoint(RECEIPT_EXPORT_FIXTURE_ROUTES)

    for method, path in MIGRATED_ROUTES:
        assert required_hybrid_regression_permissions(method, path) == (
            BACKGROUND_JOB_PERMISSION,
            FIXTURE_PERMISSION,
        )
        assert required_hybrid_regression_permissions(method.lower(), path) == (
            BACKGROUND_JOB_PERMISSION,
            FIXTURE_PERMISSION,
        )

    assert required_hybrid_regression_permissions(
        "POST",
        "/api/testing/regression/all/run",
    ) == ()


@pytest.mark.parametrize("user_id", ["ip-owner", "platform-admin"])
def test_ip_owner_and_platform_admin_satisfy_both_permissions(
    monkeypatch,
    auth_engine,
    user_id,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)
    actual_context = session_request_context.require_platform_permissions_from_session(
        HYBRID_REGRESSION_REQUIRED_PERMISSIONS,
        "Bearer forged-legacy-token",
    )
    assert actual_context is expected_context
    assert actual_context.user_id == user_id


@pytest.mark.parametrize(
    "user_id",
    [
        "superuser",
        "support-reader",
        "frontteam",
        "ordinary-admin",
        "ordinary-owner",
    ],
)
def test_roles_without_dual_platform_authority_are_denied(
    monkeypatch,
    auth_engine,
    user_id,
):
    _bind_context(monkeypatch, auth_engine, user_id)
    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permissions_from_session(
            HYBRID_REGRESSION_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("user_id", "missing_permission"),
    [
        ("job-only", FIXTURE_PERMISSION),
        ("fixture-only", BACKGROUND_JOB_PERMISSION),
    ],
)
def test_one_permission_is_never_enough(
    monkeypatch,
    auth_engine,
    user_id,
    missing_permission,
):
    _bind_context(monkeypatch, auth_engine, user_id)
    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permissions_from_session(
            HYBRID_REGRESSION_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {missing_permission}"


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
        session_request_context.require_platform_permissions_from_session(
            HYBRID_REGRESSION_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_admin_revocation_is_effective_on_next_dual_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    assert (
        session_request_context.require_platform_permissions_from_session(
            HYBRID_REGRESSION_REQUIRED_PERMISSIONS
        ).user_id
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
        session_request_context.require_platform_permissions_from_session(
            HYBRID_REGRESSION_REQUIRED_PERMISSIONS
        )
    assert exc.value.status_code == 403


def test_hybrid_routes_are_removed_from_legacy_superuser_guard():
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_ROUTES)


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


def test_both_runtime_handlers_exist_and_have_no_local_legacy_admin_guard():
    routes = _route_nodes()
    for route in MIGRATED_ROUTES:
        assert route in routes
        legacy_calls = [
            item
            for item in ast.walk(routes[route])
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "require_platform_admin_user"
        ]
        assert not legacy_calls


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


def test_session_middleware_checks_both_hybrid_permissions_before_dispatch():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_session = _call_lines(node, "bind_request_session")
    classify = _call_lines(node, "required_hybrid_regression_permissions")
    require_both = _call_lines(node, "require_platform_permissions_from_session")
    dispatch = _call_lines(node, "call_next")

    assert len(bind_session) == 1
    assert len(classify) == 1
    assert len(require_both) >= 1
    assert len(dispatch) == 1
    hybrid_require = min(line for line in require_both if line > classify[0])
    assert bind_session[0] < classify[0] < hybrid_require < dispatch[0]
