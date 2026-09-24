#!/usr/bin/env python3
"""Reject hardcoded revision literals in code that must follow the Alembic head."""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVISION_RE = re.compile(r"^\d{8}_\d+$")
HEAD_SYMBOLS = {
    "HEAD_REVISION",
    "ALEMBIC_HEAD",
    "ALEMBIC_HEAD_REVISION",
    "EXPECTED_ALEMBIC_HEAD",
    "EXPECTED_HEAD_REVISION",
}
TEXT_HEAD_FOLLOWERS = (
    ".github/workflows/postgresql-catalog-off-request-portability.yml",
)

HEAD_FOLLOWERS = (
    "backend/app/maintenance/postgresql_data_migration_head.py",
    "backend/app/maintenance/postgresql_legacy_production_adoption.py",
    "backend/app/maintenance/postgresql_legacy_production_rebuild.py",
    "backend/tests/migration_foundation_head_selftest.py",
    "backend/tests/support_message_migrated_fixture.py",
    "backend/tests/postgresql_catalog_off_request_dml_only_selftest.py",
)


def assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def violations_for_source(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        watched = sorted(set(assigned_names(node)) & HEAD_SYMBOLS)
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
    for relative in HEAD_FOLLOWERS:
        path = ROOT / relative
        if not path.is_file():
            violations.append(f"{relative}:0:missing_head_follower")
            continue
        try:
            source = path.read_text(encoding="utf-8")
            violations.extend(violations_for_source(source, relative))
        except SyntaxError as exc:
            violations.append(f"{relative}:{exc.lineno or 0}:syntax_error")
    for relative in TEXT_HEAD_FOLLOWERS:
        path = ROOT / relative
        if not path.is_file():
            violations.append(f"{relative}:0:missing_text_head_follower")
            continue
        text = path.read_text(encoding="utf-8")
        for match in REVISION_RE.finditer(text):
            violations.append(f"{relative}:0:hardcoded_revision={match.group(0)}")
    return violations


def self_test() -> None:
    bad = violations_for_source('HEAD_REVISION = "20260921_01"\n', "bad.py")
    assert bad == ["bad.py:1:HEAD_REVISION=20260921_01"]
    assert not violations_for_source(
        "HEAD_REVISION = repository_head_revision()\n", "dynamic.py"
    )
    assert not violations_for_source('BASELINE_REVISION = "20260921_01"\n', "historical.py")
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
            "FAIL hardcoded Alembic head revision literal in current-head follower; "
            "use app.alembic_head_authority.repository_head_revision() instead"
        )
    print(f"ALEMBIC_HEAD_FOLLOWER_COUNT={len(HEAD_FOLLOWERS)}")
    print(f"ALEMBIC_HEAD_TEXT_FOLLOWER_COUNT={len(TEXT_HEAD_FOLLOWERS)}")
    print("ALEMBIC_HEAD_LITERAL_SCAN_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
