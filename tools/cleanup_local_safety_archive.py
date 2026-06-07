from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_GLOB = "_local_safety_before_sync_*"
EXCLUDED_REFERENCE_PATHS = {
    Path("docs/technical/_generated/python-file-inventory.md"),
    Path("docs/technical/_generated/python-file-inventory.json"),
    Path("docs/technical/REFACTOR-ROADMAP.md"),
    Path("tools/cleanup_local_safety_archive.py"),
}
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


def should_skip(path: Path) -> bool:
    relative = rel(path)
    if any(part in SKIP_DIR_NAMES for part in relative.parts):
        return True
    if relative in EXCLUDED_REFERENCE_PATHS:
        return True
    return False


def find_archive_dirs() -> list[Path]:
    return sorted(path for path in ROOT.glob(ARCHIVE_GLOB) if path.is_dir())


def find_external_references(archive_dirs: list[Path]) -> list[str]:
    archive_names = [path.name for path in archive_dirs]
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        relative = rel(path)
        if relative.parts and relative.parts[0] in archive_names:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for archive_name in archive_names:
            if archive_name in text:
                hits.append(f"{relative.as_posix()} -> {archive_name}")
    return hits


def run_inventory() -> None:
    script = ROOT / "tools" / "generate_python_module_inventory.py"
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)


def main() -> None:
    archive_dirs = find_archive_dirs()
    if not archive_dirs:
        print("OK: geen _local_safety_before_sync_* mappen gevonden.")
        run_inventory()
        return

    print("Gevonden lokale safety-archives:")
    for archive_dir in archive_dirs:
        print(f"- {rel(archive_dir).as_posix()}")

    references = find_external_references(archive_dirs)
    if references:
        print("NIET VERWIJDERD: externe verwijzingen gevonden buiten toegestane documentatie/tooling:")
        for hit in references:
            print(f"- {hit}")
        raise SystemExit(1)

    for archive_dir in archive_dirs:
        shutil.rmtree(archive_dir)
        print(f"Verwijderd: {rel(archive_dir).as_posix()}")

    run_inventory()
    print("OK: lokale safety-archives verwijderd en Python-inventaris opnieuw gegenereerd.")


if __name__ == "__main__":
    main()
