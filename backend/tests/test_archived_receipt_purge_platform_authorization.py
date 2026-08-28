from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services import session_request_context
from app.services.archived_receipt_purge_route_authorization import (
    ARCHIVED_RECEIPT_PURGE_PERMISSION,
    archived_receipt_purge_household_context,
    bind_archived_receipt_purge_platform_context,
    required_archived_receipt_purge_permission,
    reset_archived_receipt_purge_platform_context,
)
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.authorization_schema_fixture import install_authorization_schema


PERMISSION = "platform.recovery.manage"
ROUTE_PATH = "/api/admin/receipts/purge-archived"
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


def test_classifier_is_exact_and_reuses_recovery_permission():
    assert ARCHIVED_RECEIPT_PURGE_PERMISSION == PERMISSION
    assert required_archived_receipt_purge_permission("POST", ROUTE_PATH) == PERMISSION
    assert required_archived_receipt_purge_permission("post", ROUTE_PATH) == PERMISSION
    assert required_archived_receipt_purge_permission("GET", ROUTE_PATH) is None
    assert required_archived_receipt_purge_permission("POST", f"{ROUTE_PATH}/extra") is None
    assert required_archived_receipt_purge_permission("POST", "/api/admin/receipts") is None


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
def test_receipt_purge_uses_registered_platform_role_matrix(
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


def test_request_scoped_recovery_context_preserves_explicit_household_target():
    context = _context("platform-admin")
    assert context.active_household_id is None
    assert archived_receipt_purge_household_context("household-target") is None

    token = bind_archived_receipt_purge_platform_context(context)
    try:
        target_context = archived_receipt_purge_household_context("  household-target  ")
        assert target_context is not None
        assert target_context["user_id"] == "platform-admin"
        assert target_context["active_household_id"] == "household-target"
        assert target_context["household_id"] == "household-target"
        assert target_context["display_role"] == "platform_recovery"
        assert target_context["membership_count"] == 0
    finally:
        reset_archived_receipt_purge_platform_context(token)

    assert archived_receipt_purge_household_context("household-target") is None


def test_empty_recovery_target_does_not_fall_back_to_session_household():
    token = bind_archived_receipt_purge_platform_context(_context("ip-owner"))
    try:
        target_context = archived_receipt_purge_household_context("   ")
        assert target_context is not None
        assert target_context["active_household_id"] is None
        assert target_context["household_id"] is None
    finally:
        reset_archived_receipt_purge_platform_context(token)


def _function_node(path: Path, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise AssertionError(f"Functie ontbreekt: {function_name}")


def _named_calls(node: ast.AST, function_name: str) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == function_name
    ]


def test_runtime_handler_keeps_explicit_payload_target_and_destructive_purge_logic():
    node = _function_node(MAIN_SOURCE_PATH, "purge_archived_receipts")
    calls = list(ast.walk(node))
    household_calls = [
        call
        for call in calls
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "require_household_admin_context"
    ]
    assert len(household_calls) == 1

    source = ast.get_source_segment(MAIN_SOURCE_PATH.read_text(encoding="utf-8-sig"), node)
    assert source is not None
    assert "payload.household_id" in source
    assert "deleted_at IS NOT NULL" in source
    assert "DELETE FROM purchase_import_lines" in source
    assert "DELETE FROM purchase_import_batches" in source
    assert "DELETE FROM receipt_table_lines" in source
    assert "DELETE FROM receipt_tables" in source
    assert "DELETE FROM raw_receipts" in source
    assert 'detail="household_id is verplicht"' in source


def test_session_boundary_enforces_recovery_permission_before_dispatch_and_binds_target_bridge():
    source = SESSION_ENTRYPOINT_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert "required_archived_receipt_purge_permission" in source
    assert "bind_archived_receipt_purge_platform_context" in source
    assert "reset_archived_receipt_purge_platform_context" in source
    assert "legacy_main.require_household_admin_context = require_household_admin_with_platform_recovery" in source

    middleware = _function_node(SESSION_ENTRYPOINT_SOURCE_PATH, "server_session_request_context")
    permission_calls = _named_calls(middleware, "required_archived_receipt_purge_permission")
    enforce_calls = _named_calls(middleware, "require_platform_permission_from_session")
    bind_calls = _named_calls(middleware, "bind_archived_receipt_purge_platform_context")
    dispatch_calls = _named_calls(middleware, "call_next")

    assert len(permission_calls) == 1
    assert len(bind_calls) == 1
    assert len(dispatch_calls) == 1
    assert enforce_calls
    assert permission_calls[0].lineno < bind_calls[0].lineno < dispatch_calls[0].lineno


def test_household_admin_bridge_falls_back_outside_recovery_request():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "require_household_admin_with_platform_recovery",
    )
    assert len(_named_calls(node, "archived_receipt_purge_household_context")) == 1
    assert len(_named_calls(node, "require_household_admin_from_session")) == 1
