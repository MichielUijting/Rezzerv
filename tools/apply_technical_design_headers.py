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


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def guess_header(path: Path) -> str:
    p = rel(path)
    if p == "backend/app/main.py":
        section = "TD-02 Backend API-laag"
        role = "FastAPI entrypoint and route container"
        runtime = "production"
        refactor = "split"
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
    elif p.endswith("backend/app/services/receipt_ssot_status.py") or p.endswith("/receipt_ssot_status.py"):
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
    elif p.startswith("tools/"):
        section = "TD-09 Tools en scripts"
        role = "Repository maintenance or migration helper"
        runtime = "tool"
        refactor = "classify"
        status_authority = "no"
    else:
        section = "UNCLASSIFIED"
        role = "To be classified in PYTHON-MODULE-CATALOG.md"
        runtime = "unknown"
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
    # Keep shebang and encoding comments first.
    lines = text.splitlines(keepends=True)
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    if idx < len(lines) and "coding" in lines[idx]:
        idx += 1
    return sum(len(line) for line in lines[:idx])


def main() -> None:
    changed = 0
    skipped = 0
    for path in sorted(ROOT.rglob("*.py")):
        if should_skip(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Technical Design Reference:" in text[:2000]:
            skipped += 1
            continue
        idx = insertion_index(text)
        path.write_text(text[:idx] + guess_header(path) + text[idx:], encoding="utf-8")
        changed += 1
    print(f"OK: headers added to {changed} Python files; skipped existing headers: {skipped}")
    print("Run tools/generate_python_module_inventory.py afterwards to refresh header coverage.")


if __name__ == "__main__":
    main()
