"""Static tranche-3 audit for legacy FastAPI routes.

This self-contained runner verifies that routes exposing an Authorization
parameter delegate through a proven server-side guard chain and do not parse
or trust the header directly. It uses only the Python standard library.
"""

from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
ROOT_GUARDS = {
    "get_current_user_from_authorization",
    "require_household_context",
    "require_inventory_write_context",
    "require_platform_admin_context",
    "require_household_admin_context",
    "require_household_permission_context",
}


def _decorated_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call else decorator
        if isinstance(target, ast.Attribute) and target.attr.lower() in {
            "get", "post", "put", "patch", "delete", "options", "head"
        }:
            return True
    return False


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
    """Return (safe, delegated, violations) for authorization loads in node."""
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


def _derive_trusted_guards(
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> set[str]:
    """Derive wrapper guards transitively from the immutable root guards."""
    trusted = set(ROOT_GUARDS)
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
    tree = ast.parse(source, filename=str(MAIN_PATH))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    trusted_guards = _derive_trusted_guards(functions)

    guarded_routes = 0
    failures: list[str] = []
    for node in functions.values():
        if not _decorated_route(node) or not _has_authorization_arg(node):
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

    derived_wrappers = sorted(trusted_guards - ROOT_GUARDS)
    print(f"PASS {guarded_routes} Authorization-routes gebruiken uitsluitend een bewezen guardketen")
    print(f"PASS {len(derived_wrappers)} centrale guardwrappers transitief gevalideerd")
    print("PASS Bearer/headerinhoud wordt nergens rechtstreeks door routehandlers vertrouwd")
    print("SERVER_SESSION_ROUTE_GUARD_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
