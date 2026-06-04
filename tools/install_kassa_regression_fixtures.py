from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        print("Gebruik: python tools/install_kassa_regression_fixtures.py <pad-naar-supermarkten_incl_picnic.zip>")
        return 2

    zip_path = Path(sys.argv[1]).expanduser().resolve()
    if not zip_path.exists() or not zip_path.is_file():
        print(f"Zipbestand niet gevonden: {zip_path}")
        return 2

    root = repo_root()
    manifest_path = root / "backend" / "app" / "testing" / "kassa_regression" / "manifest.json"
    raw_dir = root / "backend" / "app" / "testing" / "kassa_regression" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases") or []
    expected_count = int(manifest.get("required_receipt_count") or 18)
    if len(cases) != expected_count:
        print(f"Manifest bevat {len(cases)} cases; verwacht {expected_count}.")
        return 1

    expected_targets = {str(case.get("filename") or "").strip() for case in cases if case.get("filename")}
    for existing in raw_dir.iterdir():
        if existing.is_file() and existing.name not in expected_targets:
            existing.unlink()

    with zipfile.ZipFile(zip_path) as zf:
        names = {info.filename: info for info in zf.infolist() if not info.is_dir()}
        missing = []
        copied = []
        for case in cases:
            source_name = str(case.get("source_filename") or "").strip()
            target_name = str(case.get("filename") or "").strip()
            if not source_name or not target_name:
                missing.append(f"case {case.get('id')}: source_filename of filename ontbreekt")
                continue
            if source_name not in names:
                missing.append(source_name)
                continue
            target_path = raw_dir / target_name
            with zf.open(names[source_name]) as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            copied.append(target_name)

    if missing:
        print("Niet alle regressiebestanden zijn gevonden in de zip:")
        for item in missing:
            print(f"- {item}")
        return 1

    print(f"Kassa baseline V8 fixtures geïnstalleerd: {len(copied)} bestand(en)")
    for item in copied:
        print(f"- backend/app/testing/kassa_regression/raw/{item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
