from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = BACKEND_ROOT / "app" / "services"
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260829_10_household_product_use_case_authority.py"
)
SCOPE_FILES = (
    "household_product_use_case_service.py",
    "household_capability_expansion_service.py",
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
}


def _scope_paths() -> tuple[Path, ...]:
    paths = tuple(SERVICE_ROOT / filename for filename in SCOPE_FILES)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"PR2k onboarding scope files ontbreken: {missing}")
    if not MIGRATION_PATH.is_file():
        raise AssertionError(f"PR2k Alembic revision ontbreekt: {MIGRATION_PATH}")
    return paths


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


def _text_sql_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    sql: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_text = (
            isinstance(func, ast.Name) and func.id == "text"
        ) or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if not is_text:
            continue
        value = _string_value(node.args[0])
        if value is not None:
            sql.append(value)
    return sql


def _assert_runtime_sql_portable() -> None:
    failures: list[str] = []
    for path in _scope_paths():
        source = path.read_text(encoding="utf-8-sig")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")
    if failures:
        raise AssertionError(
            "PR2k onboarding/use-case runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_ONBOARDING_USE_CASE_SQL_PORTABLE_GREEN")
    print("POSTGRESQL_ONBOARDING_USE_CASE_RUNTIME_DDL_ABSENT_GREEN")


def _assert_validation_only_contract() -> None:
    source = (SERVICE_ROOT / "household_product_use_case_service.py").read_text(
        encoding="utf-8-sig"
    )
    required = (
        "from sqlalchemy import inspect, text",
        "def ensure_household_product_use_case_foundation",
        'inspector.has_table("household_product_use_cases")',
        'inspector.get_columns("household_product_use_cases")',
        "ON CONFLICT(household_id, use_case) DO NOTHING",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(
            f"PR2k validation/DML-only contract incomplete: {missing}"
        )
    print("POSTGRESQL_ONBOARDING_USE_CASE_VALIDATION_ONLY_SCHEMA_GREEN")


def _assert_alembic_authority() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8-sig")
    required = (
        'revision: str = "20260829_10"',
        'down_revision: Union[str, None] = "20260829_09"',
        '_TABLE = "household_product_use_cases"',
        "op.create_table(",
        "sa.PrimaryKeyConstraint(\"household_id\", \"use_case\")",
        "ck_household_product_use_cases_use_case",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"PR2k Alembic authority contract incomplete: {missing}")
    print("POSTGRESQL_ONBOARDING_USE_CASE_ALEMBIC_AUTHORITY_GREEN")


def main() -> None:
    scope = _scope_paths()
    print(f"POSTGRESQL_ONBOARDING_USE_CASE_SCOPE_GREEN service_files={len(scope)}")
    _assert_runtime_sql_portable()
    _assert_validation_only_contract()
    _assert_alembic_authority()
    print("POSTGRESQL_ONBOARDING_USE_CASE_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
