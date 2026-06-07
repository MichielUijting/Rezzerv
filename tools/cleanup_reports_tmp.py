from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "technical" / "_generated" / "python-file-inventory.json"
CATEGORY = "reports_tmp"
EXCLUDED_REFERENCE_PATHS = {
    Path("docs/technical/_generated/python-file-inventory.md"),
    Path("docs/technical/_generated/python-file-inventory.json"),
    Path("docs/technical/REFACTOR-ROADMAP.md"),
    Path("tools/cleanup_local_safety_archive.py"),
    Path("tools/cleanup_root_debug_scripts.py"),
    Path("tools/cleanup_legacy_patch_tools.py"),
    Path("tools/cleanup_reports_tmp.py"),
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


def find_external_references(candidates: list[Path]) -> dict[Path, list[str]]:
    candidate_by_name: dict[str, list[Path]] = defaultdict(list)
    candidate_by_path: dict[str, Path] = {}

    for candidate in candidates:
        relative_text = rel(candidate).as_posix()
        candidate_by_path[relative_text] = candidate
        candidate_by_name[candidate.name].append(candidate)

    references: dict[Path, list[str]] = {candidate: [] for candidate in candidates}

    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip_reference_scan(path):
            continue
        relative = rel(path)
        relative_text = relative.as_posix()
        if relative_text in candidate_by_path:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for candidate_path, candidate in sorted(candidate_by_path.items()):
            if candidate_path in text:
                references[candidate].append(f"{relative_text} -> {candidate_path}")
        for candidate_name, matching_candidates in sorted(candidate_by_name.items()):
            if candidate_name in text:
                for candidate in matching_candidates:
                    references[candidate].append(f"{relative_text} -> {candidate_name}")

    return {candidate: sorted(set(hits)) for candidate, hits in references.items()}


def run_inventory() -> None:
    script = ROOT / "tools" / "generate_python_module_inventory.py"
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)


def main() -> None:
    candidates = load_candidates()
    if not candidates:
        print("OK: geen reports_tmp Python-bestanden gevonden.")
        run_inventory()
        return

    print("Gevonden reports_tmp-kandidaten:")
    for candidate in candidates:
        print(f"- {rel(candidate).as_posix()}")

    references = find_external_references(candidates)
    blocked = {candidate: hits for candidate, hits in references.items() if hits}
    removable = [candidate for candidate in candidates if not references.get(candidate)]

    print("")
    print(f"Te verwijderen zonder externe verwijzingen: {len(removable)}")
    for candidate in removable:
        print(f"REMOVE: {rel(candidate).as_posix()}")

    print("")
    print(f"Geblokkeerd door externe verwijzingen: {len(blocked)}")
    for candidate, hits in sorted(blocked.items(), key=lambda item: rel(item[0]).as_posix()):
        print(f"BLOCKED: {rel(candidate).as_posix()}")
        for hit in hits:
            print(f"  - {hit}")

    if not removable:
        print("")
        print("NIETS VERWIJDERD: alle reports_tmp bestanden hebben externe verwijzingen.")
        return

    for candidate in removable:
        candidate.unlink()
        print(f"Verwijderd: {rel(candidate).as_posix()}")

    run_inventory()
    print("")
    print("OK: niet-gerefereerde reports_tmp Python-bestanden verwijderd en Python-inventaris opnieuw gegenereerd.")
    if blocked:
        print("Let op: geblokkeerde reports_tmp bestanden zijn blijven staan en moeten apart worden beoordeeld.")


if __name__ == "__main__":
    main()
