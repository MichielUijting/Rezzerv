from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# These modules are infrastructure/migration boundaries rather than production
# request-path SQL authority. SQLite compatibility inside db.py remains valid
# until the final production-only cutover; migration modules are allowed DDL.
EXCLUDED_RELATIVE_PATHS = {
    Path("db.py"),
    Path("migration_db.py"),
    Path("schema_migration_preflight.py"),
}
EXCLUDED_TOP_LEVEL_DIRS = {"testing", "__pycache__"}

SQL_SIGNAL = re.compile(
    r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PRAGMA|WITH)\b",
    re.IGNORECASE,
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "CREATE TRIGGER": re.compile(r"\bCREATE\s+TRIGGER\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP schema object": re.compile(
        r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE
    ),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
    "SQLite datetime()": re.compile(r"\bdatetime\s*\(", re.IGNORECASE),
    "SQLite date()": re.compile(r"\bdate\s*\(", re.IGNORECASE),
    "SQLite strftime()": re.compile(r"\bstrftime\s*\(", re.IGNORECASE),
}


def _production_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if relative in EXCLUDED_RELATIVE_PATHS:
            continue
        if relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL_DIRS:
            continue
        paths.append(path)
    if not paths:
        raise AssertionError("PR2k residual audit resolved no production Python files")
    return tuple(paths)


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return None


def _sql_like_literals(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    literals: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        value = _string_value(node)
        if value is None or not SQL_SIGNAL.search(value):
            continue
        literals.append((getattr(node, "lineno", 0), value))
    return literals


def _assert_no_hard_postgresql_blockers(paths: tuple[Path, ...]) -> None:
    failures: list[str] = []
    scanned_literals = 0
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for lineno, sql in _sql_like_literals(source):
            scanned_literals += 1
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    relative = path.relative_to(BACKEND_ROOT)
                    failures.append(f"{relative}:{lineno}: {label}")

    print(
        "POSTGRESQL_RESIDUAL_RUNTIME_SQL_SCAN_GREEN "
        f"production_files={len(paths)} sql_like_literals={scanned_literals}"
    )
    if failures:
        raise AssertionError(
            "PR2k residual PostgreSQL audit found hard production SQL blockers:\n- "
            + "\n- ".join(sorted(set(failures)))
        )
    print("POSTGRESQL_RESIDUAL_RUNTIME_SQL_HARD_BLOCKERS_ABSENT_GREEN")


def main() -> None:
    paths = _production_paths()
    _assert_no_hard_postgresql_blockers(paths)
    print("POSTGRESQL_RESIDUAL_RUNTIME_SQL_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
