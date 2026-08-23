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
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


PERMISSION = "platform.technical_configuration.manage"
ROUTE_PATH = "/api/admin/product-groups/import-gpc-nl"
BUNDLED_ROUTE_PATH = "/api/admin/product-groups/import-gpc-en-bundled"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "product_inventory_group_routes.py"
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"
IMPORT_SERVICE_SOURCE_PATH = BACKEND_ROOT / "app" / "services" / "gpc_import_service.py"


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
def test_gpc_nl_import_uses_registered_platform_role_matrix(
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


def _route_node(function_name: str) -> ast.FunctionDef:
    tree = ast.parse(ROUTE_SOURCE_PATH.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"Routefunctie ontbreekt: {function_name}")


def _call_names(node: ast.AST) -> list[tuple[str, int, ast.Call]]:
    result: list[tuple[str, int, ast.Call]] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name):
            result.append((call.func.id, call.lineno, call))
    return result


def test_gpc_nl_route_checks_canonical_permission_before_import():
    node = _route_node("admin_product_groups_import_gpc_nl")
    argument_names = {arg.arg for arg in node.args.args}
    assert "authorization" in argument_names
    assert "x_rezzerv_admin_key" not in argument_names

    calls = _call_names(node)
    permission_calls = [item for item in calls if item[0] == "require_platform_permission_from_session"]
    import_calls = [item for item in calls if item[0] == "import_gs1_gpc_nl"]
    admin_key_calls = [item for item in calls if item[0] == "require_admin_key"]

    assert len(permission_calls) == 1
    assert len(import_calls) == 1
    assert admin_key_calls == []

    permission_call = permission_calls[0][2]
    assert permission_call.args
    assert isinstance(permission_call.args[0], ast.Constant)
    assert permission_call.args[0].value == PERMISSION
    assert permission_calls[0][1] < import_calls[0][1]


def test_bundled_gpc_import_keeps_its_existing_admin_key_boundary():
    node = _route_node("admin_product_groups_import_gpc_en_bundled")
    argument_names = {arg.arg for arg in node.args.args}
    assert "x_rezzerv_admin_key" in argument_names
    assert "authorization" not in argument_names

    calls = _call_names(node)
    assert len([item for item in calls if item[0] == "require_admin_key"]) == 1
    assert len([item for item in calls if item[0] == "import_bundled_gpc_catalog"]) == 1
    assert [item for item in calls if item[0] == "require_platform_permission_from_session"] == []


def test_gpc_nl_route_is_active_and_removed_from_legacy_superuser_guard():
    source = MAIN_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert "from app.api.product_inventory_group_routes import router as product_inventory_group_router" in source
    assert "app.include_router(product_inventory_group_router)" in source
    assert ("POST", ROUTE_PATH) not in PROTECTED_MUTATIONS
    assert ("POST", "/api/admin/external-relations/batch/decision") not in PROTECTED_MUTATIONS
    assert ("POST", "/api/admin/receipts/purge-archived") not in PROTECTED_MUTATIONS
    assert len(PROTECTED_MUTATIONS) == 0


def test_gpc_nl_import_is_technical_reference_data_mutation_not_household_inventory():
    source = IMPORT_SERVICE_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert "def import_gs1_gpc_nl()" in source
    assert "_ensure_gpc_schema(conn)" in source
    assert "_upsert_gpc_row" in source
    assert "_upsert_rezzerv_product_group" in source
    assert '"mutates_inventory": False' in source


def test_gpc_nl_route_decorator_and_bundled_route_remain_distinct():
    source = ROUTE_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert f"@router.post('{ROUTE_PATH}')" in source
    assert f"@router.post('{BUNDLED_ROUTE_PATH}')" in source
