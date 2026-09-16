#!/usr/bin/env python3
"""Cheap fail-closed release preflight for expensive PR regression gates.

Checks version-file synchronization and requires an incremented app version when
runtime/release-relevant paths changed compared with the PR base commit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"^Rezzerv-MVP-v(\d+)\.(\d+)\.(\d+)$")
RELEASE_RELEVANT_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^VERSION\.txt$",
        r"^backend/VERSION\.txt$",
        r"^version\.json$",
        r"^frontend/version\.json$",
        r"^frontend/public/version\.json$",
        r"^frontend/package\.json$",
        r"^sync-version\.bat$",
        r"^bump-version\.bat$",
        r"^validate-version-sync\.bat$",
        r"^release\.bat$",
        r"^\.github/workflows/release-version-sync-validation\.yml$",
        r"^\.github/workflows/pr253-v0112109-release-package\.yml$",
        r"^backend/app/",
        r"^backend/alembic/",
        r"^backend/receipt_ingestion/",
        r"^backend/data/",
        r"^backend/Dockerfile$",
        r"^backend/requirements\.txt$",
        r"^frontend/src/",
        r"^frontend/public/(?!version\.json$)",
        r"^frontend/index\.html$",
        r"^frontend/nginx\.conf$",
        r"^frontend/Dockerfile$",
        r"^frontend/package-lock\.json$",
        r"^docker-compose.*\.yml$",
        r"^Dockerfile$",
        r"^docker/",
        r"^nginx/",
        r"^config/",
        r"^start\.bat$",
    )
)


def fail(message: str) -> None:
    raise SystemExit(f"[ERROR] {message}")


def read_text(path: str) -> str:
    full = ROOT / path
    if not full.is_file():
        fail(f"Verplicht versiebestand ontbreekt: {path}")
    return full.read_text(encoding="utf-8").strip()


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        fail(f"Ongeldig Rezzerv-versieformaat: {value}")
    return tuple(int(match.group(i)) for i in range(1, 4))


def validate_sync() -> str:
    expected = read_text("VERSION.txt")
    parse_version(expected)

    if read_text("backend/VERSION.txt") != expected:
        fail("backend/VERSION.txt is niet synchroon met VERSION.txt")

    for path in ("version.json", "frontend/version.json", "frontend/public/version.json"):
        try:
            actual = str(json.loads(read_text(path))["version"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            fail(f"Kan versie niet lezen uit {path}: {exc}")
        if actual != expected:
            fail(f"Versiemismatch in {path}: {actual} != {expected}")

    major, minor, patch = parse_version(expected)
    expected_package = f"{major}.{minor}.{patch}"
    try:
        package_version = str(json.loads(read_text("frontend/package.json"))["version"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        fail(f"Kan versie niet lezen uit frontend/package.json: {exc}")
    if package_version != expected_package:
        fail(
            "Versiemismatch in frontend/package.json: "
            f"{package_version} != {expected_package}"
        )

    return expected


def git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        fail(f"git {' '.join(args)} faalde: {process.stderr.strip()}")
    return process.stdout.strip()


def is_release_relevant(path: str) -> bool:
    return any(pattern.search(path) for pattern in RELEASE_RELEVANT_PATTERNS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    args = parser.parse_args()

    head_version = validate_sync()
    git("cat-file", "-e", f"{args.base_sha}^{{commit}}")
    changed_paths = [
        line.strip()
        for line in git("diff", "--name-only", args.base_sha, "HEAD").splitlines()
        if line.strip()
    ]
    release_relevant = sorted({path for path in changed_paths if is_release_relevant(path)})

    if not release_relevant:
        print("[OK] Alleen niet-runtimebestanden gewijzigd; geen appversieverhoging vereist.")
        print("F7_VERSION_PREFLIGHT_GREEN")
        return

    base_version = git("show", f"{args.base_sha}:VERSION.txt").strip()
    if parse_version(head_version) <= parse_version(base_version):
        print("[ERROR] Runtime-/release-relevante wijzigingen:")
        for path in release_relevant:
            print(f" - {path}")
        fail(
            "Applicatieversie is niet verhoogd vóór Full Regression: "
            f"basis={base_version}, kandidaat={head_version}. "
            "Verhoog en synchroniseer de versie terwijl de PR Draft is, en maak hem pas daarna Ready."
        )

    print(f"[OK] Applicatieversie verhoogd: {base_version} -> {head_version}")
    print("F7_VERSION_PREFLIGHT_GREEN")


if __name__ == "__main__":
    main()
