"""Static tranche-3 audit for legacy FastAPI routes.

This self-contained runner verifies that routes exposing an Authorization
parameter delegate through a proven server-side guard chain and do not parse
or trust the header directly. Runtime-replaced legacy helpers are accepted only
when their replacement assignment is present in ``session_entrypoint.py``.
Routes migrated to canonical middleware permission boundaries are accepted only
when their exact route classifier and server-session enforcement are present.
No active route may still call the historical ``require_platform_admin_user``
helper.
"""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_ROOT / "app" / "main.py"
ENTRYPOINT_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"
SESSION_CONTEXT_PATH = BACKEND_ROOT / "app" / "services" / "session_request_context.py"
FIXTURE_ROUTE_AUTH_PATH = (
    BACKEND_ROOT / "app" / "services" / "receipt_export_fixture_route_authorization.py"
)
FIXTURE_LIFECYCLE_ROUTE_AUTH_PATH = (
    BACKEND_ROOT / "app" / "services" / "fixture_lifecycle_route_authorization.py"
)
PURCHASE_IMPORT_DIAGNOSTICS_ROUTE_AUTH_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "purchase_import_batch_diagnostics_route_authorization.py"
)
TESTING_STATUS_ROUTE_AUTH_PATH = (
    BACKEND_ROOT / "app" / "services" / "testing_status_route_authorization.py"
)
ROOT_GUARDS = {
    "get_current_user_from_authorization",
    "require_household_context",
    "require_inventory_write_context",
    "require_platform_admin_context",
    "require_household_admin_context",
    "require_household_permission_context",
}
RUNTIME_REPLACED_GUARDS = {
    "resolve_authorized_household_id": "authorized_household_id_from_session",
    "get_request_household_id": "request_household_id_from_session",
}
CANONICAL_RECEIPT_EXPORT_PERMISSION_ROUTES = {
    ("/api/testing/fixtures/receipt-export/generate", "POST"),
}
CANONICAL_FIXTURE_LIFECYCLE_PERMISSION_ROUTES = {
    ("/api/testing/diagnostics/store-location-options", "POST"),
    ("/api/testing/fixtures/browser-regression/reset", "POST"),
    ("/api/testing/fixtures/cleanup", "POST"),
    ("/api/testing/fixtures/inventory/ensure", "POST"),
    ("/api/testing/fixtures/receipt-layer1/generate", "POST"),
    ("/api/testing/fixtures/receipts/seed-kassa", "POST"),
}
TESTING_STATUS_ROUTE = ("/api/testing/status", "GET")
PURCHASE_IMPORT_DIAGNOSTICS_ROUTE = (
    "/api/testing/diagnostics/purchase-import-batches/{batch_id}",
    "GET",
)
CANONICAL_MIDDLEWARE_PERMISSION_ROUTES = (
    CANONICAL_RECEIPT_EXPORT_PERMISSION_ROUTES
    | CANONICAL_FIXTURE_LIFECYCLE_PERMISSION_ROUTES
    | {TESTING_STATUS_ROUTE, PURCHASE_IMPORT_DIAGNOSTICS_ROUTE}
)
RECEIPT_EXPORT_DOWNLOAD_ROUTE = (
    "/api/testing/fixtures/receipt-export/download",
    "GET",
)
RECEIPT_EXPORT_FIXTURE_PERMISSION = "platform.test_fixtures.manage"
FIXTURE_LIFECYCLE_PERMISSION = "platform.test_fixtures.manage"
TESTING_STATUS_PERMISSION = "platform.diagnostics.view"
PURCHASE_IMPORT_DIAGNOSTICS_PERMISSION = "platform.diagnostics.view"
PURCHASE_IMPORT_DIAGNOSTICS_ROUTE_PREFIX = (
    "/api/testing/diagnostics/purchase-import-batches/"
)


def _decorated_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call else decorator
        if isinstance(target, ast.Attribute) and target.attr.lower() in {
            "get", "post", "put", "patch", "delete", "options", "head"
        }:
            return True
    return False


def _route_key(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            continue
        method = decorator.func.attr.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            return str(decorator.args[0].value), method
    return None


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _calls_named(node: ast.AST, function_name: str) -> bool:
    return any(
        isinstance(item, ast.Call) and _call_name(item) == function_name
        for item in ast.walk(node)
    )


def _has_authorization_arg(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(arg.arg == "authorization" for arg in (*node.args.args, *node.args.kwonlyargs))


def _authorization_uses_are_guarded(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    trusted_guards: set[str],
) -> tuple[bool, bool, list[str]]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(node):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    delegated = False
    violations: list[str] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Name) or item.id != "authorization" or not isinstance(item.ctx, ast.Load):
            continue
        parent = parents.get(item)
        if isinstance(parent, ast.Call):
            called = _call_name(parent)
            if called in trusted_guards and item in parent.args:
                delegated = True
                continue
        violations.append(f"line {getattr(item, 'lineno', '?')}: direct Authorization use")
    return not violations, delegated, violations


def _verify_runtime_replacements(entrypoint_source: str, session_context_source: str) -> set[str]:
    trusted: set[str] = set()
    for legacy_name, adapter_name in RUNTIME_REPLACED_GUARDS.items():
        assignment = f"legacy_main.{legacy_name} = {adapter_name}"
        assert assignment in entrypoint_source, f"runtimevervanging ontbreekt: {assignment}"
        trusted.add(legacy_name)

    assert "legacy_main.require_platform_admin_user =" not in entrypoint_source, (
        "legacy platform-admin runtimevervanging bestaat nog"
    )
    assert "require_platform_admin_from_session" not in entrypoint_source, (
        "legacy platform-admin sessie-adapter wordt nog geïmporteerd of gebruikt"
    )
    for removed_name in (
        "_canonical_platform_permission_grant",
        "bind_canonical_platform_permission_grant",
        "reset_canonical_platform_permission_grant",
        "require_platform_admin_from_session",
    ):
        assert removed_name not in session_context_source, (
            f"verwijderde platform-admin compatibility bestaat nog: {removed_name}"
        )

    assert "ADMIN_ONLY_RUNTIME_PATHS" not in entrypoint_source, (
        "legacy admin-only runtime pre-gate bestaat nog"
    )
    assert "/api/testing/fixtures/receipt-export/generate" not in entrypoint_source, (
        "receipt-export fixture gebruikt nog een hardcoded runtime Superuser-pad"
    )
    return trusted


def _verify_receipt_export_fixture_permission_boundary(
    entrypoint_source: str,
    fixture_route_auth_source: str,
) -> None:
    assert (
        f'RECEIPT_EXPORT_FIXTURE_PERMISSION = "{RECEIPT_EXPORT_FIXTURE_PERMISSION}"'
        in fixture_route_auth_source
    )
    assert "def required_receipt_export_fixture_permission(" in fixture_route_auth_source
    for path, method in CANONICAL_RECEIPT_EXPORT_PERMISSION_ROUTES | {RECEIPT_EXPORT_DOWNLOAD_ROUTE}:
        assert f'("{method}", "{path}")' in fixture_route_auth_source, (
            f"canonieke receipt-export routeclassificatie ontbreekt voor {method} {path}"
        )

    assert "required_receipt_export_fixture_permission(" in entrypoint_source
    assert "require_platform_permission_from_session(" in entrypoint_source
    assert "fixture_permission" in entrypoint_source


def _verify_fixture_lifecycle_permission_boundary(
    entrypoint_source: str,
    fixture_lifecycle_auth_source: str,
) -> None:
    assert (
        f'FIXTURE_LIFECYCLE_PERMISSION = "{FIXTURE_LIFECYCLE_PERMISSION}"'
        in fixture_lifecycle_auth_source
    )
    assert "def required_fixture_lifecycle_permission(" in fixture_lifecycle_auth_source
    for path, method in CANONICAL_FIXTURE_LIFECYCLE_PERMISSION_ROUTES:
        assert f'("{method}", "{path}")' in fixture_lifecycle_auth_source, (
            f"canonieke fixture-lifecycle routeclassificatie ontbreekt voor {method} {path}"
        )

    assert "required_fixture_lifecycle_permission(" in entrypoint_source
    assert "require_platform_permission_from_session(" in entrypoint_source
    assert "fixture_permission" in entrypoint_source


def _verify_testing_status_permission_boundary(
    entrypoint_source: str,
    testing_status_auth_source: str,
) -> None:
    assert f'TESTING_STATUS_PERMISSION = "{TESTING_STATUS_PERMISSION}"' in testing_status_auth_source
    assert '("GET", "/api/testing/status")' in testing_status_auth_source
    assert "def required_testing_status_permission(" in testing_status_auth_source
    assert "required_testing_status_permission(" in entrypoint_source
    assert "testing_status_permission" in entrypoint_source
    assert "require_platform_permission_from_session(" in entrypoint_source


def _verify_purchase_import_diagnostics_permission_boundary(
    entrypoint_source: str,
    purchase_import_diagnostics_auth_source: str,
) -> None:
    assert (
        f'PURCHASE_IMPORT_BATCH_DIAGNOSTICS_PERMISSION = "{PURCHASE_IMPORT_DIAGNOSTICS_PERMISSION}"'
        in purchase_import_diagnostics_auth_source
    )
    assert (
        f'"{PURCHASE_IMPORT_DIAGNOSTICS_ROUTE_PREFIX}"'
        in purchase_import_diagnostics_auth_source
    )
    assert (
        "def required_purchase_import_batch_diagnostics_permission("
        in purchase_import_diagnostics_auth_source
    )
    assert "required_purchase_import_batch_diagnostics_permission(" in entrypoint_source
    assert "purchase_import_batch_diagnostics_permission" in entrypoint_source
    assert "require_platform_permission_from_session(" in entrypoint_source


def _derive_trusted_guards(
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    runtime_guards: set[str],
) -> set[str]:
    trusted = set(ROOT_GUARDS) | set(runtime_guards)
    changed = True
    while changed:
        changed = False
        for name, node in functions.items():
            if name in trusted or not _has_authorization_arg(node):
                continue
            safe, delegated, _ = _authorization_uses_are_guarded(node, trusted)
            if safe and delegated:
                trusted.add(name)
                changed = True
    return trusted


def run() -> int:
    source = MAIN_PATH.read_text(encoding="utf-8")
    entrypoint_source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
    session_context_source = SESSION_CONTEXT_PATH.read_text(encoding="utf-8")
    fixture_route_auth_source = FIXTURE_ROUTE_AUTH_PATH.read_text(encoding="utf-8")
    fixture_lifecycle_auth_source = FIXTURE_LIFECYCLE_ROUTE_AUTH_PATH.read_text(encoding="utf-8")
    purchase_import_diagnostics_auth_source = PURCHASE_IMPORT_DIAGNOSTICS_ROUTE_AUTH_PATH.read_text(
        encoding="utf-8"
    )
    testing_status_auth_source = TESTING_STATUS_ROUTE_AUTH_PATH.read_text(encoding="utf-8")

    runtime_guards = _verify_runtime_replacements(entrypoint_source, session_context_source)
    _verify_receipt_export_fixture_permission_boundary(
        entrypoint_source,
        fixture_route_auth_source,
    )
    _verify_fixture_lifecycle_permission_boundary(
        entrypoint_source,
        fixture_lifecycle_auth_source,
    )
    _verify_testing_status_permission_boundary(
        entrypoint_source,
        testing_status_auth_source,
    )
    _verify_purchase_import_diagnostics_permission_boundary(
        entrypoint_source,
        purchase_import_diagnostics_auth_source,
    )

    tree = ast.parse(source, filename=str(MAIN_PATH))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    trusted_guards = _derive_trusted_guards(functions, runtime_guards)

    guarded_routes = 0
    failures: list[str] = []
    for node in functions.values():
        if not _decorated_route(node):
            continue

        if _calls_named(node, "require_platform_admin_user"):
            failures.append(
                f"{node.name} line {node.lineno}: actieve route gebruikt nog require_platform_admin_user"
            )
            continue

        if not _has_authorization_arg(node):
            continue

        if _route_key(node) in CANONICAL_MIDDLEWARE_PERMISSION_ROUTES:
            guarded_routes += 1
            continue

        safe, delegated, direct_uses = _authorization_uses_are_guarded(node, trusted_guards)
        if not delegated:
            failures.append(
                f"{node.name} line {node.lineno}: Authorization-parameter zonder bewezen centrale guardketen"
            )
            continue
        if not safe:
            failures.append(f"{node.name}: " + "; ".join(direct_uses))
            continue
        guarded_routes += 1

    assert guarded_routes > 0, "audit vond geen met Authorization beveiligde routes"
    if failures:
        print("FAIL server-side route guard audit")
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    derived_wrappers = sorted(trusted_guards - ROOT_GUARDS - runtime_guards)
    print(f"PASS {guarded_routes} Authorization-routes gebruiken uitsluitend een bewezen guardketen")
    print(f"PASS {len(runtime_guards)} legacy helpers aantoonbaar runtime-vervangen")
    print(f"PASS {len(derived_wrappers)} centrale guardwrappers transitief gevalideerd")
    print("PASS receipt-export POST en GET-fallback delen de canonieke test-fixture permissiegrens")
    print("PASS fixture-lifecycle routes gebruiken de canonieke test-fixture permissiegrens")
    print("PASS testing status gebruikt de canonieke diagnostics permissiegrens")
    print("PASS purchase-import batch diagnostics gebruikt de canonieke diagnostics permissiegrens")
    print("PASS geen actieve route gebruikt nog require_platform_admin_user")
    print("PASS platform-admin request-scoped compatibility is verwijderd")
    print("PASS Bearer/headerinhoud wordt nergens rechtstreeks door routehandlers vertrouwd")
    print("SERVER_SESSION_ROUTE_GUARD_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
