"""Static tranche-3 audit for legacy FastAPI routes.

This self-contained runner verifies that routes exposing an Authorization
parameter delegate to an approved server-side guard and do not parse or trust
the header directly. It uses only the Python standard library.
"""

from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
APPROVED_GUARDS = {
    "get_current_user_from_authorization",
    "require_household_context",
    "require_inventory_write_context",
    "require_platform_admin_context",
    "require_household_admin_context",
    "require_household_permission_context",
    # Bestaande centrale wrappers. Deze delegeren naar de hierboven genoemde
    # guards, die tijdens runtime door de server-side sessieadapter worden
    # geleverd.
    "resolve_authorized_household_id",
    "require_platform_admin_user",
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


def _authorization_arg(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(arg.arg == "authorization" for arg in (*node.args.args, *node.args.kwonlyargs))


def _authorization_is_only_guard_input(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, list[str]]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(node):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    violations: list[str] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Name) or item.id != "authorization" or not isinstance(item.ctx, ast.Load):
            continue
        parent = parents.get(item)
        if isinstance(parent, ast.Call):
            called = _call_name(parent)
            if called in APPROVED_GUARDS and item in parent.args:
                continue
        violations.append(f"line {getattr(item, 'lineno', '?')}: direct Authorization use")
    return not violations, violations


def run() -> int:
    source = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN_PATH))

    guarded_routes = 0
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _decorated_route(node) or not _authorization_arg(node):
            continue

        calls = {
            name
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            for name in [_call_name(child)]
            if name
        }
        guards = sorted(calls & APPROVED_GUARDS)
        if not guards:
            failures.append(
                f"{node.name} line {node.lineno}: Authorization-parameter zonder goedgekeurde centrale guard"
            )
            continue

        safe, direct_uses = _authorization_is_only_guard_input(node)
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

    print(f"PASS {guarded_routes} Authorization-routes gebruiken uitsluitend centrale guards")
    print("PASS Bearer/headerinhoud wordt nergens rechtstreeks door routehandlers vertrouwd")
    print("SERVER_SESSION_ROUTE_GUARD_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
