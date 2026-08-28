from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.maintenance_recompute_route_authorization import (
    MAINTENANCE_RECOMPUTE_PERMISSION,
    MAINTENANCE_RECOMPUTE_ROUTES,
    required_maintenance_recompute_permission,
)
from app.services.server_session_service import ServerSessionContext
from app.testing.authorization_schema_fixture import install_authorization_schema


BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"

EXPECTED_ROUTES = frozenset(
    {
        ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
        ("POST", "/api/admin/recompute-receipt-statuses"),
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


def test_maintenance_recompute_classifier_is_exact_and_reuses_background_job_permission():
    assert MAINTENANCE_RECOMPUTE_PERMISSION == BACKGROUND_JOB_PERMISSION
    assert MAINTENANCE_RECOMPUTE_ROUTES == EXPECTED_ROUTES

    for method, path in EXPECTED_ROUTES:
        assert required_maintenance_recompute_permission(method, path) == BACKGROUND_JOB_PERMISSION
        assert required_maintenance_recompute_permission(method.lower(), path) == BACKGROUND_JOB_PERMISSION

    assert required_maintenance_recompute_permission(
        "GET", "/api/admin/backfill-purchase-import-live-aliases"
    ) is None
    assert required_maintenance_recompute_permission(
        "GET", "/api/admin/recompute-receipt-statuses"
    ) is None
    assert required_maintenance_recompute_permission(
        "POST", "/api/admin/diagnose-receipt-status-baseline"
    ) is None
    assert required_maintenance_recompute_permission(
        "POST", "/api/admin/kassa-regression/run"
    ) is None


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
def test_maintenance_recompute_permission_uses_canonical_platform_role_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    expected_context = _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        actual_context = session_request_context.require_platform_permission_from_session(
            BACKGROUND_JOB_PERMISSION,
            "Bearer forged-legacy-token",
        )
        assert actual_context is expected_context
        assert actual_context.user_id == user_id
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            BACKGROUND_JOB_PERMISSION,
            "Bearer forged-legacy-token",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == (
        f"Ontbrekende platformpermissie: {BACKGROUND_JOB_PERMISSION}"
    )


def test_invalid_server_session_remains_401_despite_forged_bearer(
    monkeypatch,
    auth_engine,
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
            BACKGROUND_JOB_PERMISSION,
            "Bearer forged-legacy-token",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_platform_admin_revocation_is_effective_on_next_maintenance_permission_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    assert (
        session_request_context.require_platform_permission_from_session(
            BACKGROUND_JOB_PERMISSION
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
        session_request_context.require_platform_permission_from_session(
            BACKGROUND_JOB_PERMISSION
        )
    assert exc.value.status_code == 403


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


def test_both_runtime_maintenance_entrypoints_exist_without_local_legacy_admin_guard():
    routes = _route_nodes(MAIN_SOURCE_PATH)
    for route in EXPECTED_ROUTES:
        assert route in routes
        legacy_calls = [
            item
            for item in ast.walk(routes[route])
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "require_platform_admin_user"
        ]
        assert not legacy_calls


def test_session_middleware_checks_maintenance_permission_before_dispatch():
    source = SESSION_ENTRYPOINT_SOURCE_PATH.read_text(encoding="utf-8")
    bind_session = source.index("token = bind_request_session(request)")
    classify = source.index("required_maintenance_recompute_permission(")
    require_permission = source.index("require_platform_permission_from_session(", classify)
    dispatch = source.index("return await call_next(request)")

    assert bind_session < classify < require_permission < dispatch
    assert "maintenance_recompute_permission" in source[classify:dispatch]
