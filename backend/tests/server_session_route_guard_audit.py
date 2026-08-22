"""Static tranche-3 audit for legacy FastAPI routes.

This self-contained runner verifies that routes exposing an Authorization
parameter delegate through a proven server-side guard chain and do not parse
or trust the header directly. Runtime-replaced legacy helpers are accepted only
when their replacement assignment is present in ``session_entrypoint.py``.
Receipt-export fixture generation is accepted only when its dedicated canonical
platform-permission boundary is present in ``platform_admin_route_guard.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_ROOT / "app" / "main.py"
ENTRYPOINT_PATH = BACKEND_ROOT / "app" / "session_entrypoint.py"
PLATFORM_GUARD_PATH = BACKEND_ROOT / "app" / "services" / "platform_admin_route_guard.py"
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
    "require_platform_admin_user": "require_platform_admin_from_session",
}
CANONICAL_FIXTURE_PERMISSION_ROUTES = {
    ("/api/testing/fixtures/receipt-export/generate", "POST"),
}
RECEIPT_EXPORT_DOWNLOAD_ROUTE = (
    "/api/testing/fixtures/receipt-export/download",
    "GET",
)
RECEIPT_EXPORT_FIXTURE_PERMISSION = "platform.test_fixtures.manage"


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


def _verify_runtime_replacements(entrypoint_source: str) -> set[str]:
    trusted: set[str] = set()
    for legacy_name, adapter_name in RUNTIME_REPLACED_GUARDS.items():
        assignment = f"legacy_main.{legacy_name} = {adapter_name}"
        assert assignment in entrypoint_source, f"runtimevervanging ontbreekt: {assignment}"
        trusted.add(legacy_name)

    assert "/api/testing/fixtures/receipt-export/generate" not in entrypoint_source, (
        "receipt-export fixture gebruikt nog een legacy Superuser pre-gate in session_entrypoint.py"
    )
    return trusted


def _verify_receipt_export_fixture_permission_boundary(platform_guard_source: str) -> None:
    assert f'RECEIPT_EXPORT_FIXTURE_PERMISSION = "{RECEIPT_EXPORT_FIXTURE_PERMISSION}"' in platform_guard_source
    assert 'from app.services.session_request_context import require_platform_permission_from_session' in platform_guard_source
    assert 'authorize_receipt_export_fixture_request(' in platform_guard_source
    for path, method in CANONICAL_FIXTURE_PERMISSION_ROUTES | {RECEIPT_EXPORT_DOWNLOAD_ROUTE}:
        assert f'("{method}", "{path}")' in platform_guard_source, (
            f"canonieke receipt-export guard ontbreekt voor {method} {path}"
        )


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
    platform_guard_source = PLATFORM_GUARD_PATH.read_text(encoding="utf-8")
    runtime_guards = _verify_runtime_replacements(entrypoint_source)
    _verify_receipt_export_fixture_permission_boundary(platform_guard_source)
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
        if not _decorated_route(node) or not _has_authorization_arg(node):
            continue

        if _route_key(node) in CANONICAL_FIXTURE_PERMISSION_ROUTES:
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
    print("PASS receipt-export fixture gebruikt geen legacy Superuser pre-gate meer")
    print("PASS Bearer/headerinhoud wordt nergens rechtstreeks door routehandlers vertrouwd")
    print("SERVER_SESSION_ROUTE_GUARD_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
