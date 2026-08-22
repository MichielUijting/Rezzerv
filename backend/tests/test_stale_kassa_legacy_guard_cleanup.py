from __future__ import annotations

import ast
from pathlib import Path

from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS


BACKEND_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = BACKEND_ROOT / "app"
STALE_KASSA_ROUTES = frozenset(
    {
        ("POST", "/api/admin/kassa-regression/run"),
        ("POST", "/api/admin/kassa-smoke/run"),
    }
)
EXPECTED_REMAINING_LEGACY_MUTATIONS = frozenset(
    {
        ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
        ("POST", "/api/admin/diagnose-receipt-status-baseline"),
        ("POST", "/api/admin/external-relations/batch/decision"),
        ("POST", "/api/admin/product-groups/import-gpc-nl"),
        ("POST", "/api/admin/receipts/purge-archived"),
        ("POST", "/api/admin/recompute-receipt-statuses"),
        ("POST", "/api/admin/validate-receipt-status-baseline"),
    }
)
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorated_routes(tree: ast.AST) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in HTTP_METHODS or not decorator.args:
                continue
            path = _literal_string(decorator.args[0])
            if path is not None:
                routes.add((method, path))
    return routes


def _add_api_routes(tree: ast.AST) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_api_route" or not node.args:
            continue
        path = _literal_string(node.args[0])
        if path is None:
            continue

        methods: set[str] = set()
        for keyword in node.keywords:
            if keyword.arg != "methods":
                continue
            if isinstance(keyword.value, (ast.List, ast.Tuple, ast.Set)):
                for item in keyword.value.elts:
                    method = _literal_string(item)
                    if method:
                        methods.add(method.upper())
        if not methods:
            methods.add("GET")
        for method in methods:
            if method in HTTP_METHODS:
                routes.add((method, path))
    return routes


def _registered_literal_runtime_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for source_path in sorted(RUNTIME_ROOT.rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        routes.update(_decorated_routes(tree))
        routes.update(_add_api_routes(tree))
    return routes


def test_only_two_stale_kassa_entries_are_removed_from_legacy_guard():
    assert frozenset(PROTECTED_MUTATIONS) == EXPECTED_REMAINING_LEGACY_MUTATIONS
    assert len(PROTECTED_MUTATIONS) == 7
    assert PROTECTED_MUTATIONS.isdisjoint(STALE_KASSA_ROUTES)


def test_stale_kassa_paths_are_not_registered_as_runtime_routes_anywhere_under_app():
    registered_routes = _registered_literal_runtime_routes()
    assert registered_routes.isdisjoint(STALE_KASSA_ROUTES)
