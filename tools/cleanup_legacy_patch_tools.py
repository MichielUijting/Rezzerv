from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "technical" / "_generated" / "python-file-inventory.json"
CATEGORY = "tools_legacy_patch"
EXCLUDED_REFERENCE_PATHS = {
    Path("docs/technical/_generated/python-file-inventory.md"),
    Path("docs/technical/_generated/python-file-inventory.json"),
    Path("docs/technical/REFACTOR-ROADMAP.md"),
    Path("tools/cleanup_local_safety_archive.py"),
    Path("tools/cleanup_root_debug_scripts.py"),
    Path("tools/cleanup_legacy_patch_tools.py"),
    Path("tools/apply_technical_design_headers.py"),
    Path("tools/generate_python_module_inventory.py"),
}
EXCLUDED_REFERENCE_PREFIXES = (
    "tools/debug_output/",
    "reports/",
    "tmp/",
)
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


def rel(path: Path) -> Path:
    return path.relative_to(ROOT)


def should_skip_reference_scan(path: Path) -> bool:
    relative = rel(path)
    relative_text = relative.as_posix()
    if any(part in SKIP_DIR_NAMES for part in relative.parts):
        return True
    if relative in EXCLUDED_REFERENCE_PATHS:
        return True
    if relative_text.startswith(EXCLUDED_REFERENCE_PREFIXES):
        return True
    return False


def load_candidates() -> list[Path]:
    if not INVENTORY_PATH.exists():
        raise SystemExit(f"Inventaris ontbreekt: {INVENTORY_PATH}")
    items = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    candidates: list[Path] = []
    for item in items:
        if item.get("repository_category") == CATEGORY:
            candidate = ROOT / item["path"]
            if candidate.exists() and candidate.is_file():
                candidates.append(candidate)
    return sorted(candidates)


def find_external_references(candidates: list[Path]) -> list[str]:
    candidate_names = {candidate.name for candidate in candidates}
    candidate_paths = {rel(candidate).as_posix() for candidate in candidates}
    hits: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip_reference_scan(path):
            continue
        relative = rel(path)
        relative_text = relative.as_posix()
        if relative_text in candidate_paths:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for candidate_path in sorted(candidate_paths):
            if candidate_path in text:
                hits.append(f"{relative_text} -> {candidate_path}")
        for candidate_name in sorted(candidate_names):
            if candidate_name in text:
                hits.append(f"{relative_text} -> {candidate_name}")
    return sorted(set(hits))


def run_inventory() -> None:
    script = ROOT / "tools" / "generate_python_module_inventory.py"
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)


def main() -> None:
    candidates = load_candidates()
    if not candidates:
        print("OK: geen tools_legacy_patch bestanden gevonden.")
        run_inventory()
        return

    print("Gevonden tools_legacy_patch-kandidaten:")
    for candidate in candidates:
        print(f"- {rel(candidate).as_posix()}")

    references = find_external_references(candidates)
    if references:
        print("NIET VERWIJDERD: externe verwijzingen gevonden buiten toegestane documentatie/tooling:")
        for hit in references:
            print(f"- {hit}")
        raise SystemExit(1)

    for candidate in candidates:
        candidate.unlink()
        print(f"Verwijderd: {rel(candidate).as_posix()}")

    run_inventory()
    print("OK: legacy patchtools verwijderd en Python-inventaris opnieuw gegenereerd.")


if __name__ == "__main__":
    main()
