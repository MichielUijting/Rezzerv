from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "technical" / "_generated"
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}


@dataclass
class ModuleInventoryItem:
    path: str
    line_count: int
    td_section_guess: str
    runtime_type_guess: str
    refactor_status_guess: str
    imports: list[str]
    functions: list[str]
    classes: list[str]
    fastapi_routes: list[str]
    reads_data: bool
    writes_data: bool
    status_terms: list[str]
    has_technical_design_header: bool


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def parse_python(path: Path) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return [], [], [], [], []

    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    routes: list[str] = []
    status_terms: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            for decorator in node.decorator_list:
                route = route_from_decorator(decorator)
                if route:
                    routes.append(route)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.lower()
            for term in ["parse_status", "po_norm_status", "status_label", "baseline", "receipt_status"]:
                if term in value and term not in status_terms:
                    status_terms.append(term)

    return sorted(set(imports)), functions, classes, routes, sorted(status_terms)


def route_from_decorator(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    method = None
    if isinstance(func, ast.Attribute):
        method = func.attr.lower()
    if method not in {"get", "post", "patch", "put", "delete"}:
        return None
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return f"{method.upper()} {first.value}"
    return f"{method.upper()} <dynamic>"


def guess_td(path: str) -> tuple[str, str, str]:
    p = path.replace("\\", "/")
    if p.startswith("backend/app/receipt_ingestion/"):
        if "explain" in p or "diagnos" in p:
            return "TD-07 Diagnose en explainability", "diagnostic", "keep_diagnostic"
        return "TD-03 Receipt ingestion en parsers", "production", "classify"
    if p.startswith("backend/app/services/receipt_status_baseline_service"):
        if p.endswith("_v4.py"):
            return "TD-04 Status en SSOT", "compatibility", "deprecate"
        return "TD-04 Status en SSOT", "production", "keep"
    if p.endswith("backend/app/services/receipt_ssot_status.py") or p.endswith("/receipt_ssot_status.py"):
        return "TD-04 Status en SSOT", "production", "cleanup"
    if p.endswith("backend/app/main.py"):
        return "TD-02 Backend API-laag", "production", "split"
    if p.startswith("backend/app/testing") or "/testing" in p:
        return "TD-08 Test, baseline en regressie", "test", "classify"
    if p.startswith("tools/"):
        return "TD-09 Tools en scripts", "tool", "classify"
    if "gmail" in p or "email" in p or "inbound" in p:
        return "TD-06 Email, Gmail en inbound", "production", "classify"
    if p.startswith("backend/app/"):
        return "TD-05 Datastore en services", "production", "classify"
    return "UNCLASSIFIED", "unknown", "classify"


def build_item(path: Path) -> ModuleInventoryItem:
    text = path.read_text(encoding="utf-8", errors="ignore")
    imports, functions, classes, routes, status_terms = parse_python(path)
    relative_path = rel(path)
    td, runtime_type, refactor_status = guess_td(relative_path)
    reads_data = any(token in text for token in ["SELECT ", "engine.connect", "engine.begin", ".execute(", "session.query"])
    writes_data = any(token in text for token in ["INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "DROP TABLE", ".add(", ".delete("])
    return ModuleInventoryItem(
        path=relative_path,
        line_count=len(text.splitlines()),
        td_section_guess=td,
        runtime_type_guess=runtime_type,
        refactor_status_guess=refactor_status,
        imports=imports[:40],
        functions=functions[:80],
        classes=classes[:40],
        fastapi_routes=routes,
        reads_data=reads_data,
        writes_data=writes_data,
        status_terms=status_terms,
        has_technical_design_header="Technical Design Reference:" in text[:1500],
    )


def write_markdown(items: list[ModuleInventoryItem]) -> None:
    lines: list[str] = []
    lines.append("# Generated Python File Inventory")
    lines.append("")
    lines.append("Generated by `tools/generate_python_module_inventory.py`.")
    lines.append("")
    lines.append(f"Total Python files: {len(items)}")
    lines.append("")
    lines.append("| Path | Lines | TD Section | Runtime | Refactor | Routes | DB R/W | Header |")
    lines.append("|---|---:|---|---|---|---:|---|---|")
    for item in items:
        db = f"{'R' if item.reads_data else '-'}{'W' if item.writes_data else '-'}"
        header = "yes" if item.has_technical_design_header else "no"
        lines.append(
            f"| `{item.path}` | {item.line_count} | {item.td_section_guess} | {item.runtime_type_guess} | {item.refactor_status_guess} | {len(item.fastapi_routes)} | {db} | {header} |"
        )
    lines.append("")
    lines.append("## Modules with status terms")
    lines.append("")
    for item in items:
        if item.status_terms:
            lines.append(f"- `{item.path}`: {', '.join(item.status_terms)}")
    lines.append("")
    lines.append("## Modules with FastAPI routes")
    lines.append("")
    for item in items:
        if item.fastapi_routes:
            lines.append(f"### `{item.path}`")
            for route in item.fastapi_routes:
                lines.append(f"- `{route}`")
            lines.append("")
    (OUTPUT_DIR / "python-file-inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    py_files = sorted(path for path in ROOT.rglob("*.py") if not should_skip(path))
    items = [build_item(path) for path in py_files]
    (OUTPUT_DIR / "python-file-inventory.json").write_text(
        json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(items)
    print(f"OK: inventoried {len(items)} Python files")
    print(f"- {OUTPUT_DIR / 'python-file-inventory.md'}")
    print(f"- {OUTPUT_DIR / 'python-file-inventory.json'}")


if __name__ == "__main__":
    main()
