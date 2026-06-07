"""
Technical Design Reference:
- TD Section: TD-09 Tools en scripts
- Module Role: Repository maintenance helper
- Runtime Type: tool
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

import ast
import fnmatch
import json
import warnings
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

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

STATUS_TERMS = ["parse_status", "po_norm_status", "status_label", "baseline", "receipt_status"]
ROOT_DEBUG_PATTERNS = (
    "dump_*.py",
    "peek_*.py",
    "inspect_*.py",
    "map_*.py",
    "receipt_duplicates.py",
)
LEGACY_TOOL_PATTERNS = (
    "tools/apply_r*.py",
    "tools/apply_R*.py",
    "tools/patch*.py",
    "tools/r7*.py",
    "tools/R9-*.py",
    "tools/R9_*.py",
    "tools/HOTFIX*.py",
)
ACTIVE_TOOL_ALLOWLIST = {
    "tools/generate_python_module_inventory.py",
    "tools/apply_technical_design_headers.py",
    "tools/install_kassa_regression_fixtures.py",
    "tools/remove_legacy_email_import_route.py",
    "tools/r7c33_receipt_validation_runner.py",
}


@dataclass
class ModuleInventoryItem:
    path: str
    repository_category: str
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
    header_scope_default: bool


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def repository_category(path: str) -> str:
    p = path.replace("\\", "/")
    name = Path(p).name

    if p.startswith("_local_safety_before_sync_"):
        return "local_safety_archive"
    if p.startswith("deprecated/"):
        return "deprecated"
    if p.startswith("reports/") or p.startswith("tmp/"):
        return "reports_tmp"
    if p.startswith("backend/tests/"):
        return "backend_tests"
    if p.startswith("backend/app/testing") or "diagnos" in p or "explain" in p:
        return "diagnostics"
    if p.startswith("backend/app/api/routes/") or p.startswith("backend/app/api/"):
        # Some API routes are production, some diagnostic. Use status by naming.
        if any(token in p for token in ("diagnos", "debug", "smoke", "regression", "snapshot", "kpi", "dev_", "testing")):
            return "diagnostics"
        return "active_backend_app"
    if p.startswith("backend/app/"):
        return "active_backend_app"
    if p.startswith("backend/receipt_ingestion/"):
        return "legacy_backend_module"
    if p.startswith("backend/"):
        if name.startswith("test_") or p.startswith("backend/tests/"):
            return "backend_tests"
        return "backend_support"
    if p.startswith("tools/"):
        if p in ACTIVE_TOOL_ALLOWLIST:
            return "tools_active"
        if matches_any(p, LEGACY_TOOL_PATTERNS):
            return "tools_legacy_patch"
        return "tools_active"
    if matches_any(p, ROOT_DEBUG_PATTERNS):
        return "root_debug_scripts"
    if p.startswith("frontend/"):
        return "root_debug_scripts"
    return "unclassified"


def parse_python(path: Path) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
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
            for term in STATUS_TERMS:
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


def guess_td(path: str, category: str) -> tuple[str, str, str]:
    p = path.replace("\\", "/")
    if category == "local_safety_archive":
        return "TD-09 Tools en scripts", "archive", "remove-candidate"
    if category == "deprecated":
        return "TD-09 Tools en scripts", "deprecated", "remove-candidate"
    if category == "reports_tmp":
        return "TD-08 Test, baseline en regressie", "report/tmp", "remove-candidate"
    if category == "root_debug_scripts":
        return "TD-09 Tools en scripts", "tool", "remove-candidate"
    if category == "tools_legacy_patch":
        return "TD-09 Tools en scripts", "tool", "deprecate"
    if category == "tools_active":
        return "TD-09 Tools en scripts", "tool", "keep"
    if category == "backend_tests":
        return "TD-08 Test, baseline en regressie", "test", "keep_diagnostic"
    if category == "diagnostics":
        return "TD-07 Diagnose en explainability", "diagnostic", "keep_diagnostic"
    if p.startswith("backend/app/receipt_ingestion/"):
        return "TD-03 Receipt ingestion en parsers", "production", "classify"
    if p.startswith("backend/app/services/receipt_status_baseline_service"):
        if p.endswith("_v4.py"):
            return "TD-04 Status en SSOT", "compatibility", "deprecate"
        return "TD-04 Status en SSOT", "production", "keep"
    if p.endswith("backend/app/services/receipt_ssot_status.py") or p.endswith("/receipt_ssot_status.py"):
        return "TD-04 Status en SSOT", "production", "cleanup"
    if p.endswith("backend/app/main.py"):
        return "TD-02 Backend API-laag", "production", "split"
    if "gmail" in p or "email" in p or "inbound" in p:
        return "TD-06 Email, Gmail en inbound", "production", "classify"
    if category == "active_backend_app":
        return "TD-05 Datastore en services", "production", "classify"
    if category == "legacy_backend_module":
        return "TD-03 Receipt ingestion en parsers", "legacy", "deprecate"
    if category == "backend_support":
        return "TD-09 Tools en scripts", "tool/support", "classify"
    return "UNCLASSIFIED", "unknown", "classify"


def header_scope_default(path: str, category: str) -> bool:
    p = path.replace("\\", "/")
    if category not in {"active_backend_app", "backend_tests", "diagnostics"}:
        return False
    if p.startswith("backend/app/") or p.startswith("backend/tests/"):
        return True
    return False


def build_item(path: Path) -> ModuleInventoryItem:
    text = path.read_text(encoding="utf-8", errors="ignore")
    imports, functions, classes, routes, status_terms = parse_python(path)
    relative_path = rel(path)
    category = repository_category(relative_path)
    td, runtime_type, refactor_status = guess_td(relative_path, category)
    reads_data = any(token in text for token in ["SELECT ", "engine.connect", "engine.begin", ".execute(", "session.query"])
    writes_data = any(token in text for token in ["INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "DROP TABLE", ".add(", ".delete("])
    return ModuleInventoryItem(
        path=relative_path,
        repository_category=category,
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
        header_scope_default=header_scope_default(relative_path, category),
    )


def write_inventory(items: list[ModuleInventoryItem]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "python-file-inventory.json"
    md_path = OUTPUT_DIR / "python-file-inventory.md"

    json_path.write_text(json.dumps([asdict(item) for item in items], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = Counter(item.repository_category for item in items)
    lines = [
        "# Python Module Inventory",
        "",
        "Generated by `tools/generate_python_module_inventory.py`.",
        "",
        "## Counts by repository category",
        "",
    ]
    for category, count in sorted(counts.items()):
        lines.append(f"- `{category}`: {count}")
    lines.extend([
        "",
        "## Files",
        "",
        "| Path | Category | TD guess | Runtime | Refactor | Routes | Header | Header scope |",
        "|---|---|---|---|---|---:|---|---|",
    ])
    for item in items:
        lines.append(
            "| "
            + " | ".join([
                f"`{item.path}`",
                item.repository_category,
                item.td_section_guess,
                item.runtime_type_guess,
                item.refactor_status_guess,
                str(len(item.fastapi_routes)),
                "yes" if item.has_technical_design_header else "no",
                "yes" if item.header_scope_default else "no",
            ])
            + " |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: inventoried {len(items)} Python files")
    print("Repository categories:")
    for category, count in sorted(counts.items()):
        print(f"- {category}: {count}")
    print(f"- {md_path}")
    print(f"- {json_path}")


def main() -> None:
    items = [build_item(path) for path in sorted(ROOT.rglob("*.py")) if not should_skip(path)]
    write_inventory(items)


if __name__ == "__main__":
    main()
