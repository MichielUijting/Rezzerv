from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

SAFE_PREFIXES = (
    "backend/app/",
    "backend/tests/",
)
SAFE_TOOL_FILES = {
    "tools/generate_python_module_inventory.py",
    "tools/apply_technical_design_headers.py",
}
EXCLUDED_PREFIXES = (
    "_local_safety_before_sync_",
    "deprecated/",
    "reports/",
    "tmp/",
    "frontend/",
)
EXCLUDED_ROOT_NAMES = (
    "dump_",
    "peek_",
    "inspect_",
    "map_",
)
EXCLUDED_TOOL_PREFIXES = (
    "tools/apply_r",
    "tools/apply_R",
    "tools/patch",
    "tools/r7",
    "tools/R9-",
    "tools/R9_",
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_in_safe_scope(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    p = rel(path)
    name = path.name
    if p in SAFE_TOOL_FILES:
        return True
    if p.startswith(EXCLUDED_PREFIXES):
        return False
    if name.startswith(EXCLUDED_ROOT_NAMES) or name == "receipt_duplicates.py":
        return False
    if p.startswith(EXCLUDED_TOOL_PREFIXES):
        return False
    return p.startswith(SAFE_PREFIXES)


def guess_header(path: Path) -> str:
    p = rel(path)
    if p == "backend/app/main.py":
        section = "TD-02 Backend API-laag"
        role = "FastAPI entrypoint and route container"
        runtime = "production"
        refactor = "split"
        status_authority = "no"
    elif p.startswith("backend/app/api/") and any(token in p for token in ("diagnos", "debug", "smoke", "regression", "snapshot", "kpi", "dev_", "testing")):
        section = "TD-07 Diagnose en explainability"
        role = "Diagnostic or test API route"
        runtime = "diagnostic"
        refactor = "keep_diagnostic"
        status_authority = "no"
    elif p.startswith("backend/app/receipt_ingestion/"):
        section = "TD-03 Receipt ingestion en parsers"
        role = "Receipt source parsing and data extraction"
        runtime = "production"
        refactor = "classify"
        status_authority = "no"
    elif p.startswith("backend/app/services/receipt_status_baseline_service"):
        section = "TD-04 Status en SSOT"
        role = "PO norm status baseline authority or compatibility shim"
        runtime = "production"
        refactor = "keep/deprecate"
        status_authority = "yes only for active service"
    elif p.endswith("/receipt_ssot_status.py"):
        section = "TD-04 Status en SSOT"
        role = "Map PO norm status to API/UI fields"
        runtime = "production"
        refactor = "cleanup"
        status_authority = "no"
    elif p.startswith("backend/app/testing") or "/testing" in p:
        section = "TD-08 Test, baseline en regressie"
        role = "Test or baseline support"
        runtime = "test"
        refactor = "classify"
        status_authority = "no"
    elif p.startswith("backend/tests/"):
        section = "TD-08 Test, baseline en regressie"
        role = "Backend automated test"
        runtime = "test"
        refactor = "keep_diagnostic"
        status_authority = "no"
    elif p.startswith("tools/"):
        section = "TD-09 Tools en scripts"
        role = "Repository maintenance helper"
        runtime = "tool"
        refactor = "keep"
        status_authority = "no"
    else:
        section = "TD-05 Datastore en services"
        role = "Backend application module"
        runtime = "production"
        refactor = "classify"
        status_authority = "no"

    return f'''"""
Technical Design Reference:
- TD Section: {section}
- Module Role: {role}
- Runtime Type: {runtime}
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: {status_authority}
- Refactor Status: {refactor}
"""

'''


def insertion_index(text: str) -> int:
    lines = text.splitlines(keepends=True)
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    if idx < len(lines) and "coding" in lines[idx]:
        idx += 1
    return sum(len(line) for line in lines[:idx])


def main() -> None:
    changed = 0
    skipped_existing_header = 0
    skipped_scope = 0
    for path in sorted(ROOT.rglob("*.py")):
        if not is_in_safe_scope(path):
            skipped_scope += 1
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Technical Design Reference:" in text[:2000]:
            skipped_existing_header += 1
            continue
        idx = insertion_index(text)
        path.write_text(text[:idx] + guess_header(path) + text[idx:], encoding="utf-8")
        changed += 1
    print(f"OK: headers added to {changed} Python files")
    print(f"- skipped existing headers: {skipped_existing_header}")
    print(f"- skipped outside safe scope: {skipped_scope}")
    print("Safe scope: backend/app/, backend/tests/, and the two technical design tools only.")
    print("Run tools/generate_python_module_inventory.py afterwards to refresh header coverage.")


if __name__ == "__main__":
    main()
