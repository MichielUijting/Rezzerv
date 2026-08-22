from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import (
    ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    V2_PLATFORM_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.receipt_export_fixture_route_authorization import (
    RECEIPT_EXPORT_FIXTURE_PERMISSION,
    RECEIPT_EXPORT_FIXTURE_ROUTES,
    required_receipt_export_fixture_permission,
)
from app.services.server_session_service import ServerSessionContext


PERMISSION = "platform.test_fixtures.manage"
POST_ROUTE = ("POST", "/api/testing/fixtures/receipt-export/generate")
DOWNLOAD_ROUTE = ("GET", "/api/testing/fixtures/receipt-export/download")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"

OTHER_LEGACY_FIXTURE_MUTATIONS = {
    ("POST", "/api/testing/diagnostics/store-location-options"),
    ("POST", "/api/testing/fixtures/browser-regression/reset"),
    ("POST", "/api/testing/fixtures/cleanup"),
    ("POST", "/api/testing/fixtures/inventory/ensure"),
    ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
    ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
}


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


def test_fixture_permission_is_registered_without_broadening_superuser_targets():
    assert RECEIPT_EXPORT_FIXTURE_PERMISSION == PERMISSION
    assert PERMISSION in V2_PLATFORM_PERMISSIONS
    assert PERMISSION in PLATFORM_ADMIN_PERMISSIONS
    assert PERMISSION not in ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS
    assert PERMISSION not in V2_SUPERUSER_TARGET_PERMISSIONS


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
def test_fixture_permission_uses_registered_platform_role_matrix(
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
        session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer forged-legacy-token",
        )

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


def test_receipt_export_http_entrypoints_share_one_canonical_permission_boundary():
    assert RECEIPT_EXPORT_FIXTURE_ROUTES == frozenset({POST_ROUTE, DOWNLOAD_ROUTE})
    for method, path in RECEIPT_EXPORT_FIXTURE_ROUTES:
        assert required_receipt_export_fixture_permission(method, path) == PERMISSION
    assert (
        required_receipt_export_fixture_permission(
            "GET",
            "/api/testing/reports/complete",
        )
        is None
    )


def test_receipt_export_generate_is_removed_from_legacy_superuser_guard_only():
    assert POST_ROUTE not in PROTECTED_MUTATIONS
    for route in OTHER_LEGACY_FIXTURE_MUTATIONS:
        assert route in PROTECTED_MUTATIONS


def _function_node(
    path: Path,
    function_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    assert len(matches) == 1, function_name
    return matches[0]


def test_download_fallback_that_can_generate_fixture_is_inside_canonical_guard_boundary():
    node = _function_node(MAIN_SOURCE_PATH, "export_receipt_export_fixture")
    generator_calls = [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == "generate_receipt_export_fixture"
    ]
    assert len(generator_calls) == 1
    assert DOWNLOAD_ROUTE in RECEIPT_EXPORT_FIXTURE_ROUTES


def _call_lines(node: ast.AST, call_name: str) -> list[int]:
    return sorted(
        item.lineno
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == call_name
    )


def test_fixture_permission_check_runs_after_session_bind_and_before_route_dispatch():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_lines = _call_lines(node, "bind_request_session")
    classify_lines = _call_lines(node, "required_receipt_export_fixture_permission")
    permission_lines = _call_lines(node, "require_platform_permission_from_session")
    dispatch_lines = _call_lines(node, "call_next")

    assert len(bind_lines) == 1
    assert len(classify_lines) == 1
    assert len(permission_lines) == 1
    assert len(dispatch_lines) == 1
    assert bind_lines[0] < classify_lines[0] < permission_lines[0] < dispatch_lines[0]


def test_receipt_export_no_longer_uses_runtime_superuser_pre_gate():
    source = SESSION_ENTRYPOINT_SOURCE_PATH.read_text(encoding="utf-8")
    assert "/api/testing/fixtures/receipt-export/generate" not in source
    assert "ADMIN_ONLY_RUNTIME_PATHS" not in source
