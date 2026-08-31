"""Fail-closed audit for SQLite use in normal test infrastructure.

The production datastore is PostgreSQL. Normal application, API, session,
authorization and frontend-regression tests must therefore not silently create
or select SQLite databases. Explicit historical migration/compatibility tests
may remain SQLite-backed, but only through this file's exact path+pattern
allowlist with a documented reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SELF_PATH = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()


@dataclass(frozen=True)
class Pattern:
    key: str
    regex: re.Pattern[str]
    description: str


PATTERNS = (
    Pattern(
        "sqlite_url",
        re.compile(r"sqlite(?:\+pysqlite)?://", re.IGNORECASE),
        "SQLite SQLAlchemy URL",
    ),
    Pattern(
        "sqlite_module",
        re.compile(r"(?:^|\s)(?:import\s+sqlite3\b|from\s+sqlite3\b)|\bsqlite3\.(?:connect|Connection|Row)\b"),
        "sqlite3 module/runtime connection",
    ),
    Pattern(
        "sqlite_catalog",
        re.compile(r"\bsqlite_master\b", re.IGNORECASE),
        "SQLite catalog access",
    ),
    Pattern(
        "sqlite_pragma",
        re.compile(r"\bPRAGMA\b", re.IGNORECASE),
        "SQLite PRAGMA",
    ),
    Pattern(
        "sqlite_threading",
        re.compile(r"check_same_thread"),
        "SQLite check_same_thread harness",
    ),
    Pattern(
        "legacy_authorization_schema_fixture",
        re.compile(r"app\.testing\.authorization_schema_fixture"),
        "legacy mini authorization schema fixture",
    ),
    Pattern(
        "legacy_server_session_schema_fixture",
        re.compile(r"app\.testing\.server_session_contract"),
        "legacy mini server-session schema fixture",
    ),
    Pattern(
        "legacy_onboarding_schema_fixture",
        re.compile(r"app\.testing\.onboarding_request_schema_fixture"),
        "legacy mini onboarding schema fixture",
    ),
)


# Exact compatibility boundaries only. No directory wildcards are permitted.
# A path may allow only the named pattern classes; any other SQLite construct
# in that file still fails the audit.
ALLOWED_BOUNDARIES: dict[str, dict[str, str]] = {
    "backend/tests/test_authorization_membership_service.py": {
        "sqlite_url": (
            "Historical household_memberships layouts are intentionally built "
            "in isolation to prove legacy-to-canonical role migration semantics."
        ),
        "legacy_authorization_schema_fixture": (
            "The legacy membership migration contract needs the isolated "
            "authorization target schema before exercising historical source layouts."
        ),
    },
    "backend/tests/platform_feature_flag_migrated_fixture.py": {
        "sqlite_url": (
            "Explicit Alembic-on-SQLite compatibility fallback; normal CI selects "
            "the configured PostgreSQL DATABASE_URL first."
        ),
    },
}


TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".ps1", ".bat", ".sh"}
SCRIPT_TEST_KEYWORDS = (
    "test",
    "regression",
    "validation",
    "selftest",
    "audit",
)


def _is_scanned_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    relative = path.relative_to(REPO_ROOT).as_posix()
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


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def main() -> int:
    scanned_files = 0
    allowed_hits: list[tuple[str, int, str, str]] = []
    violations: list[tuple[str, int, str, str]] = []

    for path in sorted(REPO_ROOT.rglob("*")):
        if not _is_scanned_file(path):
            continue
        scanned_files += 1
        relative = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="strict")
        allowances = ALLOWED_BOUNDARIES.get(relative, {})

        for pattern in PATTERNS:
            for match in pattern.regex.finditer(text):
                line = _line_number(text, match.start())
                excerpt = text.splitlines()[line - 1].strip()
                reason = allowances.get(pattern.key)
                if reason:
                    allowed_hits.append((relative, line, pattern.key, reason))
                else:
                    violations.append((relative, line, pattern.key, excerpt))

    # Prevent stale allowlist entries from silently accumulating.
    allowed_paths_seen = {item[0] for item in allowed_hits}
    stale_paths = sorted(set(ALLOWED_BOUNDARIES) - allowed_paths_seen)
    for relative in stale_paths:
        violations.append(
            (
                relative,
                0,
                "stale_allowlist",
                "Allowlisted path has no matching SQLite compatibility boundary anymore",
            )
        )

    for relative, line, pattern_key, reason in allowed_hits:
        print(
            "SQLITE_COMPATIBILITY_BOUNDARY_ALLOWED "
            f"path={relative} line={line} pattern={pattern_key} reason={reason}"
        )

    if violations:
        print("SQLITE_TEST_INFRASTRUCTURE_RESIDUAL_RED", file=sys.stderr)
        for relative, line, pattern_key, excerpt in violations:
            print(
                f"RED path={relative} line={line} pattern={pattern_key} :: {excerpt}",
                file=sys.stderr,
            )
        print(
            f"RESULT scanned_files={scanned_files} allowed_hits={len(allowed_hits)} "
            f"violations={len(violations)}",
            file=sys.stderr,
        )
        return 1

    print(
        "POSTGRESQL_TEST_INFRASTRUCTURE_RESIDUAL_SCAN_GREEN "
        f"scanned_files={scanned_files} allowed_hits={len(allowed_hits)} violations=0"
    )
    print("POSTGRESQL_TEST_INFRASTRUCTURE_BOUNDARY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
