from __future__ import annotations

import ast
from pathlib import Path

from app.services.purchase_import_batch_diagnostics_route_authorization import (
    PURCHASE_IMPORT_BATCH_DIAGNOSTICS_PERMISSION,
    PURCHASE_IMPORT_BATCH_DIAGNOSTICS_ROUTE_PREFIX,
    required_purchase_import_batch_diagnostics_permission,
)
from app.services.testing_status_route_authorization import TESTING_STATUS_PERMISSION


PERMISSION = "platform.diagnostics.view"
ROUTE = (
    "GET",
    "/api/testing/diagnostics/purchase-import-batches/{batch_id}",
)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE_PATH = BACKEND_ROOT / "app" / "main.py"
SESSION_ENTRYPOINT_SOURCE_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"


def test_purchase_import_batch_diagnostics_reuses_approved_diagnostics_permission():
    assert PURCHASE_IMPORT_BATCH_DIAGNOSTICS_PERMISSION == PERMISSION
    assert TESTING_STATUS_PERMISSION == PERMISSION
    assert (
        PURCHASE_IMPORT_BATCH_DIAGNOSTICS_ROUTE_PREFIX
        == "/api/testing/diagnostics/purchase-import-batches/"
    )


def test_purchase_import_batch_diagnostics_classifier_is_exact():
    path = "/api/testing/diagnostics/purchase-import-batches/batch-123"
    assert required_purchase_import_batch_diagnostics_permission("GET", path) == PERMISSION
    assert required_purchase_import_batch_diagnostics_permission("get", path) == PERMISSION
    assert required_purchase_import_batch_diagnostics_permission("POST", path) is None
    assert (
        required_purchase_import_batch_diagnostics_permission(
            "GET",
            "/api/testing/diagnostics/purchase-import-batches/",
        )
        is None
    )
    assert (
        required_purchase_import_batch_diagnostics_permission(
            "GET",
            "/api/testing/diagnostics/purchase-import-batches/batch-123/extra",
        )
        is None
    )
    assert required_purchase_import_batch_diagnostics_permission("GET", "/api/testing/status") is None


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


def _named_calls(node: ast.AST, function_name: str) -> list[ast.Call]:
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == function_name
    ]


def test_purchase_import_batch_diagnostics_handler_has_no_legacy_platform_admin_call():
    routes = _route_nodes()
    node = routes[ROUTE]
    assert _named_calls(node, "require_platform_admin_user") == []


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
    return sorted(call.lineno for call in _named_calls(node, call_name))


def test_purchase_import_diagnostics_permission_runs_before_dispatch():
    node = _function_node(
        SESSION_ENTRYPOINT_SOURCE_PATH,
        "server_session_request_context",
    )
    bind_lines = _call_lines(node, "bind_request_session")
    classify_lines = _call_lines(
        node,
        "required_purchase_import_batch_diagnostics_permission",
    )
    permission_lines = _call_lines(node, "require_platform_permission_from_session")
    dispatch_lines = _call_lines(node, "call_next")

    assert len(bind_lines) == 1
    assert len(classify_lines) == 1
    assert permission_lines
    assert len(dispatch_lines) == 1
    assert bind_lines[0] < classify_lines[0] < dispatch_lines[0]
    assert any(classify_lines[0] < line < dispatch_lines[0] for line in permission_lines)
