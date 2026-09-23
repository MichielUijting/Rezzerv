#!/usr/bin/env python3
"""Self-tests for canonical version-only carry-forward detection."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("version_only_carry_forward.py")
spec = importlib.util.spec_from_file_location("version_only_carry_forward", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FILES = [
    "VERSION.txt",
    "backend/VERSION.txt",
    "version.json",
    "frontend/version.json",
    "frontend/public/version.json",
    "frontend/package.json",
]
POLICY = {
    "policy_id": "F7-RISK-01",
    "version_only_bundle": {
        "files": FILES,
        "json_version_only_files": [
            "version.json",
            "frontend/version.json",
            "frontend/public/version.json",
            "frontend/package.json",
        ],
    },
    "version_only_carry_forward": {
        "enabled": True,
        "require_direct_parent": True,
        "require_exact_bundle": True,
        "require_patch_increment": 1,
    },
}


def run(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def write_bundle(root: Path, patch: int, *, package_name: str = "rezzerv-frontend") -> None:
    release = f"Rezzerv-MVP-v01.12.{patch}"
    package = f"1.12.{patch}"
    (root / "backend").mkdir(exist_ok=True)
    (root / "frontend/public").mkdir(parents=True, exist_ok=True)
    (root / "VERSION.txt").write_text(release + "\n", encoding="utf-8")
    (root / "backend/VERSION.txt").write_text(release + "\n", encoding="utf-8")
    for path in ("version.json", "frontend/version.json", "frontend/public/version.json"):
        (root / path).write_text(json.dumps({"version": release}) + "\n", encoding="utf-8")
    (root / "frontend/package.json").write_text(
        json.dumps({"name": package_name, "private": True, "version": package}, indent=2) + "\n",
        encoding="utf-8",
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    run(root, "init", "-q")
    run(root, "config", "user.email", "ci@example.test")
    run(root, "config", "user.name", "CI")

    write_bundle(root, 174)
    (root / "app.txt").write_text("stable\n", encoding="utf-8")
    run(root, "add", ".")
    run(root, "commit", "-qm", "base")
    base = run(root, "rev-parse", "HEAD")

    write_bundle(root, 175)
    run(root, "add", ".")
    run(root, "commit", "-qm", "version")
    good = run(root, "rev-parse", "HEAD")
    result = module.canonical_version_only_delta(root, POLICY, base, good)
    assert result["safe"] is True, result
    assert result["reason"] == "canonical_version_only"

    run(root, "checkout", "-q", "-b", "bad-app", base)
    write_bundle(root, 175)
    (root / "app.txt").write_text("changed\n", encoding="utf-8")
    run(root, "add", ".")
    run(root, "commit", "-qm", "bad app")
    bad_app = run(root, "rev-parse", "HEAD")
    assert module.canonical_version_only_delta(root, POLICY, base, bad_app)["safe"] is False

    run(root, "checkout", "-q", "-b", "bad-json", base)
    write_bundle(root, 175, package_name="changed-name")
    run(root, "add", ".")
    run(root, "commit", "-qm", "bad json")
    bad_json = run(root, "rev-parse", "HEAD")
    bad_result = module.canonical_version_only_delta(root, POLICY, base, bad_json)
    assert bad_result["safe"] is False
    assert str(bad_result["reason"]).startswith("json_non_version_change:")

    run(root, "checkout", "-q", "-b", "two-steps", base)
    write_bundle(root, 175)
    run(root, "add", ".")
    run(root, "commit", "-qm", "175")
    write_bundle(root, 176)
    run(root, "add", ".")
    run(root, "commit", "-qm", "176")
    two_steps = run(root, "rev-parse", "HEAD")
    two_result = module.canonical_version_only_delta(root, POLICY, base, two_steps)
    assert two_result["safe"] is False
    assert two_result["reason"] == "not_direct_parent"

print("VERSION_ONLY_CARRY_FORWARD_SELFTEST_GREEN")
