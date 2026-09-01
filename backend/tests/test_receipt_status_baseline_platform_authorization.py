from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services import session_request_context
from app.services.maintenance_recompute_route_authorization import MAINTENANCE_RECOMPUTE_ROUTES
from app.services.receipt_status_baseline_route_authorization import (
    RECEIPT_STATUS_BASELINE_DIAGNOSTICS_PERMISSION,
    RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS,
    RECEIPT_STATUS_BASELINE_ROUTES,
    RECEIPT_STATUS_BASELINE_TECHNICAL_PERMISSION,
    required_receipt_status_baseline_permissions,
)
from app.services.server_session_service import ServerSessionContext
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.postgresql_onboarding_selftest_fixture import reset_postgresql_test_database
from app.testing.postgresql_platform_authorization_fixture import create_platform_authorization_test_engine


DIAGNOSTICS_PERMISSION = "platform.diagnostics.view"
TECHNICAL_PERMISSION = "platform.technical_configuration.manage"
MIGRATED_ROUTES = frozenset(
    {
        ("POST", "/api/admin/diagnose-receipt-status-baseline"),
        ("POST", "/api/admin/validate-receipt-status-baseline"),
    }
)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"
BASELINE_SERVICE_SOURCE_PATH = BACKEND_ROOT / "app" / "services" / "receipt_status_baseline_service.py"


@pytest.fixture
def auth_engine():
    reset_postgresql_test_database()
    engine = create_platform_authorization_test_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_roles(role_key, scope, name, system_role, active)
            VALUES
              ('platform.diagnostics_only_test', 'platform', 'Diagnostics only test role', FALSE, TRUE),
              ('platform.technical_only_test', 'platform', 'Technical only test role', FALSE, TRUE)
        """))
        conn.execute(text("""
            INSERT INTO auth_role_permissions(role_key, permission_key)
            VALUES
              ('platform.diagnostics_only_test', 'platform.diagnostics.view'),
              ('platform.technical_only_test', 'platform.technical_configuration.manage')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('diagnostics-only', 'platform.diagnostics_only_test', TRUE),
              ('technical-only', 'platform.technical_only_test', TRUE)
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
    elif user_id in {"platform-admin", "diagnostics-only", "technical-only"}:
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


def test_receipt_status_baseline_classifier_is_exact_and_requires_both_permissions():
    assert RECEIPT_STATUS_BASELINE_DIAGNOSTICS_PERMISSION == DIAGNOSTICS_PERMISSION
    assert RECEIPT_STATUS_BASELINE_TECHNICAL_PERMISSION == TECHNICAL_PERMISSION
    assert RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS == (
        DIAGNOSTICS_PERMISSION,
        TECHNICAL_PERMISSION,
    )
    assert RECEIPT_STATUS_BASELINE_ROUTES == MIGRATED_ROUTES
    assert RECEIPT_STATUS_BASELINE_ROUTES.isdisjoint(MAINTENANCE_RECOMPUTE_ROUTES)

    for method, path in MIGRATED_ROUTES:
        assert required_receipt_status_baseline_permissions(method, path) == (
            DIAGNOSTICS_PERMISSION,
            TECHNICAL_PERMISSION,
        )
        assert required_receipt_status_baseline_permissions(method.lower(), path) == (
            DIAGNOSTICS_PERMISSION,
            TECHNICAL_PERMISSION,
        )

    assert required_receipt_status_baseline_permissions(
        "GET", "/api/admin/diagnose-receipt-status-baseline"
    ) == ()
    assert required_receipt_status_baseline_permissions(
        "GET", "/api/admin/validate-receipt-status-baseline"
    ) == ()
    assert required_receipt_status_baseline_permissions(
        "POST", "/api/admin/recompute-receipt-statuses"
    ) == ()


@pytest.mark.parametrize("user_id", ["ip-owner", "platform-admin"])
def test_ip_owner_and_platform_admin_satisfy_both_baseline_permissions(
    monkeypatch,
    auth_engine,
    user_id,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)
    actual_context = session_request_context.require_platform_permissions_from_session(
        RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS,
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
def test_roles_without_dual_baseline_authority_are_denied(
    monkeypatch,
    auth_engine,
    user_id,
):
    _bind_context(monkeypatch, auth_engine, user_id)
    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permissions_from_session(
            RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("user_id", "missing_permission"),
    [
        ("diagnostics-only", TECHNICAL_PERMISSION),
        ("technical-only", DIAGNOSTICS_PERMISSION),
    ],
)
def test_one_baseline_permission_is_never_enough(
    monkeypatch,
    auth_engine,
    user_id,
    missing_permission,
):
    _bind_context(monkeypatch, auth_engine, user_id)
    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permissions_from_session(
            RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {missing_permission}"


def test_invalid_server_session_remains_401_despite_forged_bearer(monkeypatch, auth_engine):
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
            RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_admin_revocation_is_effective_on_next_baseline_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    assert (
        session_request_context.require_platform_permissions_from_session(
            RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS
        ).user_id
        == "platform-admin"
    )

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = FALSE
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permissions_from_session(
            RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS
        )
    assert exc.value.status_code == 403


def _route_nodes() -> dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(MAIN_SOURCE_PATH.read_text(encoding="utf-8-sig"))
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


def test_both_runtime_baseline_handlers_exist_without_local_legacy_admin_guard():
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


def test_dual_permission_requirement_is_justified_by_service_write_capability():
    source = BASELINE_SERVICE_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert "ALTER TABLE receipt_tables ADD COLUMN store_chain TEXT" not in source
    assert "UPDATE receipt_tables SET store_chain = :store_chain WHERE id = :id" in source
    assert "_ensure_receipt_store_chain_schema(conn)" in source
    assert "Voer Alembic migrations uit met MIGRATION_DATABASE_URL" in source


def _function_node(path: Path, function_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
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


def test_session_middleware_checks_both_baseline_permissions_before_dispatch():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_session = _call_lines(node, "bind_request_session")
    classify = _call_lines(node, "required_receipt_status_baseline_permissions")
    require_both = _call_lines(node, "require_platform_permissions_from_session")
    dispatch = _call_lines(node, "call_next")

    assert len(bind_session) == 1
    assert len(classify) == 1
    assert len(require_both) >= 2
    assert len(dispatch) == 1
    baseline_require = min(line for line in require_both if line > classify[0])
    assert bind_session[0] < classify[0] < baseline_require < dispatch[0]
