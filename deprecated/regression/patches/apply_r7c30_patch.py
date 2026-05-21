from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PATCH_NAME = "R7c30_rewrite_regression_runner.patch"
TARGET = Path("frontend/scripts/run-regression.mjs")
START = "*** BEGIN R7C30 FULL FILE ***"
END = "*** END R7C30 FULL FILE ***"


def read_payload(patch_path: Path) -> str:
    text = patch_path.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"Patchbestand mist {START!r} of {END!r}")
    return text.split(START, 1)[1].split(END, 1)[0].strip() + "\n"


def main() -> None:
    root = Path.cwd()
    target = root / TARGET
    patch_path = root / "tools" / PATCH_NAME
    if not patch_path.exists():
        patch_path = root / PATCH_NAME
    if not patch_path.exists():
        raise SystemExit(f"Patchbestand niet gevonden: tools/{PATCH_NAME} of {PATCH_NAME}")
    if not target.exists():
        raise SystemExit(f"Doelbestand niet gevonden: {TARGET}")

    payload = read_payload(patch_path)
    backup = target.with_suffix(target.suffix + ".r7c30_bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(target, backup)
    target.write_text(payload, encoding="utf-8")

    print("R7c-30 patch toegepast")
    print(f"Doelbestand: {TARGET}")
    print(f"Backup: {backup}")
    print("Volgende stap: cd frontend; npm run regression")


if __name__ == "__main__":
    main()
