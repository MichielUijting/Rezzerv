from __future__ import annotations

import ast
from pathlib import Path
import re


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
DDL_PATTERN = re.compile(
    r"\b(?:CREATE\s+(?:TABLE|INDEX)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX)|PRAGMA\s+table_info)\b",
    flags=re.IGNORECASE,
)
IMPORTED_SCHEMA_MUTATORS = {
    "ensure_article_group_schema",
}
ALLOWED_TOP_LEVEL_SCHEMA_VALIDATORS = {
    "ensure_external_article_product_link_schema",
}


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _contains_schema_mutation(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(function_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if DDL_PATTERN.search(node.value):
                return True
        if isinstance(node, ast.Call) and _call_name(node.func).endswith(".create_all"):
            return True
    return False


def _startup_nodes(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from _startup_nodes(child)


def main() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(MAIN_PATH))
    local_schema_mutators = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _contains_schema_mutation(node)
    }

    violations: list[str] = []
    for node in _startup_nodes(module):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        short_name = call_name.rsplit(".", 1)[-1]
        if call_name.endswith(".create_all"):
            violations.append(call_name)
            continue
        if short_name in ALLOWED_TOP_LEVEL_SCHEMA_VALIDATORS:
            continue
        if short_name in local_schema_mutators or short_name in IMPORTED_SCHEMA_MUTATORS:
            violations.append(call_name or short_name)

    if violations:
        raise AssertionError(
            "Production startup still executes schema mutation: "
            + ", ".join(sorted(set(violations)))
        )

    print("RUNTIME_STARTUP_SCHEMA_MUTATION_REMOVED_GREEN")


if __name__ == "__main__":
    main()
