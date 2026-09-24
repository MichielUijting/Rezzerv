#!/usr/bin/env python3
"""Reject hardcoded Alembic head revision literals outside migration files."""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (ROOT / "backend" / "app", ROOT / "backend" / "tests")
REVISION_RE = re.compile(r"^\d{8}_\d+$")
HEAD_SYMBOLS = {
    "HEAD_REVISION",
    "ALEMBIC_HEAD",
    "ALEMBIC_HEAD_REVISION",
    "EXPECTED_ALEMBIC_HEAD",
    "EXPECTED_HEAD_REVISION",
}


def assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def violations_for_source(source: str, filename: str) -> list[str]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}:{exc.lineno or 0}:syntax_error"]
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        names = set(assigned_names(node))
        watched = sorted(names & HEAD_SYMBOLS)
        if not watched:
            continue
        value_node = node.value
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            continue
        value = value_node.value.strip()
        if REVISION_RE.fullmatch(value):
            violations.append(
                f"{filename}:{getattr(node, 'lineno', 0)}:{','.join(watched)}={value}"
            )
    return violations


def scan_repository() -> list[str]:
    violations: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            violations.extend(
                violations_for_source(path.read_text(encoding="utf-8"), relative)
            )
    return violations


def self_test() -> None:
    bad = violations_for_source('HEAD_REVISION = "20260921_01"\n', "bad.py")
    assert bad == ["bad.py:1:HEAD_REVISION=20260921_01"]
    assert not violations_for_source(
        "HEAD_REVISION = repository_head_revision()\n", "dynamic.py"
    )
    assert not violations_for_source('TARGET_REVISION = "20260921_01"\n', "historical.py")
    assert not violations_for_source('HEAD_REVISION = "not-a-revision"\n', "other.py")
    print("ALEMBIC_HEAD_LITERAL_SELFTEST_GREEN")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    violations = scan_repository()
    for violation in violations:
        print(f"ALEMBIC_HEAD_LITERAL_VIOLATION={violation}")
    if violations:
        raise SystemExit(
            "FAIL hardcoded Alembic head revision literal(s); use "
            "app.alembic_head_authority.repository_head_revision() instead"
        )
    print("ALEMBIC_HEAD_LITERAL_SCAN_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
