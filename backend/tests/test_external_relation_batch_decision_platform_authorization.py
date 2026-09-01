from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services import session_request_context
from app.services.external_relation_batch_decision_route_authorization import (
    EXTERNAL_RELATION_BATCH_DECISION_PERMISSION,
    required_external_relation_batch_decision_permission,
)
from app.services.server_session_service import ServerSessionContext
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.postgresql_platform_authorization_fixture import (
    cleanup_platform_authorization_test_engine,
    create_platform_authorization_test_engine,
)


PERMISSION = "platform.external_products.link_existing"
ROUTE_PATH = "/api/admin/external-relations/batch/decision"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_ROUTES_SOURCE_PATH = BACKEND_ROOT / "app" / "api" / "system_routes.py"
STORE_SOURCE_PATH = BACKEND_ROOT / "app" / "services" / "external_relation_batch_store.py"
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"


@pytest.fixture
def auth_engine():
    engine = create_platform_authorization_test_engine()
    try:
        yield engine
    finally:
        cleanup_platform_authorization_test_engine(engine)


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


def test_classifier_is_exact_and_reuses_external_product_link_permission():
    assert EXTERNAL_RELATION_BATCH_DECISION_PERMISSION == PERMISSION
    assert required_external_relation_batch_decision_permission("POST", ROUTE_PATH) == PERMISSION
    assert required_external_relation_batch_decision_permission("post", ROUTE_PATH) == PERMISSION
    assert required_external_relation_batch_decision_permission("GET", ROUTE_PATH) is None
    assert required_external_relation_batch_decision_permission("PUT", ROUTE_PATH) is None
    assert required_external_relation_batch_decision_permission("POST", f"{ROUTE_PATH}/extra") is None
    assert required_external_relation_batch_decision_permission("POST", "/api/admin/external-relations/batch") is None


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("ip-owner", True),
        ("frontteam", True),
        ("platform-admin", False),
        ("superuser", True),
        ("support-reader", False),
        ("ordinary-admin", False),
        ("ordinary-owner", False),
    ],
)
def test_decision_route_uses_registered_platform_role_matrix(
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


def test_invalid_server_session_remains_401_even_with_forged_frontteam_bearer(
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
            PERMISSION,
            "Bearer frontteam",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"


def test_forged_frontteam_bearer_cannot_elevate_support_session(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "support-reader")

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(
            PERMISSION,
            "Bearer frontteam",
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {PERMISSION}"


def test_frontteam_revocation_is_effective_on_next_permission_check(
    monkeypatch,
    auth_engine,
):
    _bind_context(monkeypatch, auth_engine, "frontteam")

    assert (
        session_request_context.require_platform_permission_from_session(PERMISSION).user_id
        == "frontteam"
    )

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = FALSE
            WHERE user_id = 'frontteam'
              AND role_key = 'platform.frontteam'
        """))

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(PERMISSION)

    assert exc.value.status_code == 403


def test_runtime_handler_dispatches_decision_without_second_local_auth_boundary():
    node = _function_node(SYSTEM_ROUTES_SOURCE_PATH, "admin_external_relation_batch_decision")
    assert len(_named_calls(node, "apply_external_relation_batch_decision")) == 1
    assert not _named_calls(node, "require_platform_admin_user")
    assert not _named_calls(node, "require_platform_permission_from_session")
    assert not _named_calls(node, "require_household_admin_context")

    source = ast.get_source_segment(
        SYSTEM_ROUTES_SOURCE_PATH.read_text(encoding="utf-8-sig"),
        node,
    )
    assert source is not None
    assert "candidate_id" in source
    assert "household_article_id" in source
    assert "decision" in source


def test_decision_service_does_not_create_household_articles_or_inventory():
    node = _function_node(STORE_SOURCE_PATH, "apply_external_relation_batch_decision")
    source = ast.get_source_segment(STORE_SOURCE_PATH.read_text(encoding="utf-8-sig"), node)
    assert source is not None
    normalized = source.upper()

    assert "INSERT INTO HOUSEHOLD_ARTICLES" not in normalized
    assert "INSERT INTO INVENTORY" not in normalized
    assert "INSERT INTO INVENTORY_EVENTS" not in normalized
    assert "INSERT INTO PRODUCT_ENRICHMENTS" in normalized
    assert '"creates_household_article": False' in source
    assert '"creates_inventory_event": False' in source


def test_session_boundary_enforces_link_existing_before_dispatch():
    middleware = _function_node(SESSION_ENTRYPOINT_SOURCE_PATH, "server_session_request_context")
    classifier_calls = _named_calls(
        middleware,
        "required_external_relation_batch_decision_permission",
    )
    permission_calls = _named_calls(middleware, "require_platform_permission_from_session")
    dispatch_calls = _named_calls(middleware, "call_next")

    assert len(classifier_calls) == 1
    assert len(dispatch_calls) == 1
    later_permission_calls = [
        call for call in permission_calls if call.lineno > classifier_calls[0].lineno
    ]
    assert later_permission_calls
    assert classifier_calls[0].lineno < later_permission_calls[0].lineno < dispatch_calls[0].lineno

    source = SESSION_ENTRYPOINT_SOURCE_PATH.read_text(encoding="utf-8-sig")
    assert "external_relation_batch_decision_permission" in source
    assert "required_external_relation_batch_decision_permission" in source
    assert "bind_canonical_platform_permission_grant(external_relation_batch_decision_permission" not in source
