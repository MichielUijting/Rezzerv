"""Fail-closed audit for SQLite use in normal test infrastructure.

The production datastore is PostgreSQL. Normal application, API, session,
authorization and frontend-regression tests must therefore not silently create
or select SQLite databases. Explicit historical migration/compatibility tests
may remain SQLite-backed, but only through this file's exact path allowlist with
a documented reason.

Default mode is intentionally PR-blocking: scan every relevant file changed from
the locked PostgreSQL operational-cutover base. Set
REZZERV_TEST_BOUNDARY_SCAN_ALL=1 for a repository-wide debt inventory.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SELF_PATH = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
LOCKED_BASE_SHA = "4b1cff13b192abbafa03032460d0f88f243d935f"


@dataclass(frozen=True)
class Pattern:
    key: str
    regex: re.Pattern[str]
    description: str


# These expressions target execution/harness constructs, not documentation or
# static PostgreSQL audits that merely mention forbidden SQLite syntax.
PATTERNS = (
    Pattern(
        "sqlite_url",
        re.compile(r"sqlite(?:\+pysqlite)?://", re.IGNORECASE),
        "SQLite SQLAlchemy URL",
    ),
    Pattern(
        "sqlite_module_import",
        re.compile(r"(?m)^[ \t]*(?:import\s+sqlite3\b|from\s+sqlite3\b)"),
        "sqlite3 module import",
    ),
    Pattern(
        "sqlite_module_runtime",
        re.compile(r"\bsqlite3\.(?:connect|Connection|Row)\b"),
        "sqlite3 runtime connection/type",
    ),
    Pattern(
        "sqlite_pragma_runtime",
        re.compile(
            r"(?im)^.*(?:execute|exec_driver_sql)\s*\([^\n]*\bPRAGMA\b[^\n]*$"
        ),
        "executed SQLite PRAGMA",
    ),
    Pattern(
        "sqlite_catalog_runtime",
        re.compile(
            r"(?im)^.*(?:execute|exec_driver_sql)\s*\([^\n]*\bsqlite_master\b[^\n]*$"
        ),
        "executed SQLite catalog SQL",
    ),
    Pattern(
        "sqlite_threading",
        re.compile(r"check_same_thread"),
        "SQLite check_same_thread harness",
    ),
    Pattern(
        "legacy_authorization_schema_fixture",
        re.compile(r"\binstall_authorization_schema\b"),
        "legacy mini authorization schema fixture",
    ),
    Pattern(
        "legacy_server_session_schema_fixture",
        re.compile(r"\bcreate_server_session_contract_schema\b"),
        "legacy mini server-session schema fixture",
    ),
    Pattern(
        "legacy_onboarding_schema_fixture",
        re.compile(
            r"\b(?:install_household_onboarding_schema|"
            r"install_household_product_configuration_schema|install_location_schema)\b"
        ),
        "legacy mini onboarding/location schema fixture",
    ),
)


# Exact compatibility boundaries only. No directory wildcards are permitted.
# These files intentionally exercise historical SQLite source/schema behavior;
# they are not normal application-runtime test harnesses.
ALLOWED_COMPATIBILITY_FILES: dict[str, str] = {
    ".github/workflows/postgresql-data-migration-validation.yml": (
        "Validates the controlled SQLite production-source to PostgreSQL importer."
    ),
    ".github/workflows/postgresql-foundation-validation.yml": (
        "Validates the immutable SQLite baseline used to build the PostgreSQL foundation."
    ),
    ".github/workflows/postgresql-migration-foundation-validation.yml": (
        "Validates both sides of the SQLite-to-PostgreSQL migration foundation."
    ),
    "backend/tests/capture_schema_baseline.py": (
        "Captures the immutable historical SQLite schema baseline used by migration tests."
    ),
    "backend/tests/database_production_cutover_selftest.py": (
        "Asserts SQLite runtime configuration is rejected by the production cutover policy."
    ),
    "backend/tests/migration_foundation_core_selftest.py": (
        "Checks historical SQLite schema/index contracts as migration-source evidence."
    ),
    "backend/tests/migration_foundation_head_selftest.py": (
        "Checks SQLite compatibility and PostgreSQL head as a dual migration-foundation gate."
    ),
    "backend/tests/platform_feature_flag_migrated_fixture.py": (
        "Keeps an explicit Alembic-on-SQLite compatibility fallback; normal CI uses PostgreSQL."
    ),
    "backend/tests/postgresql_data_migration_selftest.py": (
        "Builds and validates SQLite source snapshots for the production data importer."
    ),
    "backend/tests/postgresql_legacy_production_adoption_selftest.py": (
        "Reconstructs historical production SQLite drift before canonical PostgreSQL adoption."
    ),
    "backend/tests/receipt_lifecycle_schema_authority_selftest.py": (
        "Proves the historical SQLite receipt schema can be migrated without runtime DDL."
    ),
    "backend/tests/schema_authority_cutover_selftest.py": (
        "Exercises historical SQLite schema-authority compatibility during Alembic cutover."
    ),
    "backend/tests/server_session_schema_authority_selftest.py": (
        "Proves historical SQLite server-session schema adoption into Alembic authority."
    ),
    "backend/tests/test_authorization_membership_service.py": (
        "Builds historical household_memberships layouts to prove legacy role migration semantics."
    ),
}


TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".ps1", ".bat", ".sh"}
SCRIPT_TEST_KEYWORDS = (
    "test",
    "regression",
    "validation",
    "selftest",
    "audit",
)


def _is_relevant_relative_path(relative: str) -> bool:
    path = Path(relative)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    if relative == SELF_PATH:
        return False
    if relative.startswith("backend/tests/"):
        return True
    if relative.startswith("backend/app/testing/"):
        return True
    if relative.startswith(".github/workflows/"):
        return True
    if relative.startswith("scripts/"):
        name = path.name.lower()
        return any(keyword in name for keyword in SCRIPT_TEST_KEYWORDS)
    return False


def _all_relevant_files() -> list[Path]:
    return [
        path
        for path in sorted(REPO_ROOT.rglob("*"))
        if path.is_file()
        and _is_relevant_relative_path(path.relative_to(REPO_ROOT).as_posix())
    ]


def _changed_relevant_files() -> list[Path]:
    base_sha = str(os.getenv("REZZERV_TEST_BOUNDARY_BASE_SHA") or LOCKED_BASE_SHA).strip()
    if not base_sha:
        raise RuntimeError("Locked boundary base SHA ontbreekt")

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        raise RuntimeError(
            f"Locked boundary base {base_sha} is geen ancestor van HEAD; heraudit vereist"
        )

    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", base_sha, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    files: list[Path] = []
    for raw in result.stdout.splitlines():
        relative = raw.strip().replace("\\", "/")
        if not relative or not _is_relevant_relative_path(relative):
            continue
        candidate = REPO_ROOT / relative
        if candidate.is_file():
            files.append(candidate)
    return sorted(set(files))


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def main() -> int:
    scan_all = str(os.getenv("REZZERV_TEST_BOUNDARY_SCAN_ALL") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    candidates = _all_relevant_files() if scan_all else _changed_relevant_files()
    candidate_relatives = {
        path.relative_to(REPO_ROOT).as_posix() for path in candidates
    }

    allowed_hits: list[tuple[str, int, str, str]] = []
    violations: list[tuple[str, int, str, str]] = []
    matched_paths: set[str] = set()

    for path in candidates:
        relative = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="strict")
        compatibility_reason = ALLOWED_COMPATIBILITY_FILES.get(relative)
        lines = text.splitlines()

        for pattern in PATTERNS:
            for match in pattern.regex.finditer(text):
                line = _line_number(text, match.start())
                excerpt = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                matched_paths.add(relative)
                if compatibility_reason:
                    allowed_hits.append(
                        (relative, line, pattern.key, compatibility_reason)
                    )
                else:
                    violations.append((relative, line, pattern.key, excerpt))

    # Prevent stale compatibility declarations only when the declared file is
    # actually in the active scan scope.
    stale_paths = sorted(
        (set(ALLOWED_COMPATIBILITY_FILES) & candidate_relatives) - matched_paths
    )
    for relative in stale_paths:
        violations.append(
            (
                relative,
                0,
                "stale_allowlist",
                "Compatibility path no longer contains a detected SQLite boundary",
            )
        )

    for relative, line, pattern_key, reason in allowed_hits:
        print(
            "SQLITE_COMPATIBILITY_BOUNDARY_ALLOWED "
            f"path={relative} line={line} pattern={pattern_key} reason={reason}"
        )

    scope = "repo" if scan_all else "changed-from-locked-base"
    if violations:
        print("SQLITE_TEST_INFRASTRUCTURE_RESIDUAL_RED", file=sys.stderr)
        for relative, line, pattern_key, excerpt in violations:
            print(
                f"RED path={relative} line={line} pattern={pattern_key} :: {excerpt}",
                file=sys.stderr,
            )
        print(
            f"RESULT scope={scope} scanned_files={len(candidates)} "
            f"allowed_hits={len(allowed_hits)} violations={len(violations)}",
            file=sys.stderr,
        )
        return 1

    print(
        "POSTGRESQL_TEST_INFRASTRUCTURE_RESIDUAL_SCAN_GREEN "
        f"scope={scope} scanned_files={len(candidates)} "
        f"allowed_hits={len(allowed_hits)} violations=0"
    )
    print("POSTGRESQL_TEST_INFRASTRUCTURE_BOUNDARY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
