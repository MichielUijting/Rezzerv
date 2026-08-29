from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = BACKEND_ROOT / "app" / "services" / "day_article_service.py"
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260829_12_day_article_direct_authority.py"
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP schema object": re.compile(r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
}


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
    source = SERVICE_PATH.read_text(encoding="utf-8-sig")
    failures: list[str] = []
    for index, sql in enumerate(_text_sql_literals(source), start=1):
        for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
            if pattern.search(sql):
                failures.append(f"day_article_service.py SQL#{index}: {label}")
    if failures:
        raise AssertionError(
            "Day-article/Direct runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    if "protected = 1" in source or "protected, 1" in source:
        raise AssertionError("Direct-location protected writes still assume integer Boolean storage")
    if "protected = TRUE" not in source:
        raise AssertionError("Direct-location PostgreSQL Boolean write contract is missing")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_SQL_PORTABLE_GREEN")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_RUNTIME_DDL_ABSENT_GREEN")


def _assert_validation_only_contract() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8-sig")
    required = (
        "def ensure_day_article_schema",
        "Validate the Alembic-owned day-article/Direct contract without mutation.",
        '"idx_spaces_household_system_key"',
        '"idx_sublocations_space_system_key"',
        '"idx_day_article_events_article"',
        "sa.Boolean",
        "sa.DateTime",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"Day-article validation-only contract incomplete: {missing}")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_VALIDATION_ONLY_SCHEMA_GREEN")


def _assert_alembic_authority() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8-sig")
    required = (
        'revision: str = "20260829_12"',
        'down_revision: Union[str, None] = "20260829_11"',
        '_EVENTS = "day_article_processing_events"',
        '"default_inventory_handling"',
        '"inventory_handling_updated_at"',
        '"inventory_handling_updated_by_user_id"',
        '"system_key"',
        '"protected"',
        "op.create_table(",
        "idx_spaces_household_system_key",
        "idx_sublocations_space_system_key",
        "idx_day_article_events_article",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"Day-article Alembic authority contract incomplete: {missing}")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_ALEMBIC_AUTHORITY_GREEN")


def main() -> None:
    if not SERVICE_PATH.is_file() or not MIGRATION_PATH.is_file():
        raise AssertionError("Day-article authority scope files ontbreken")
    _assert_runtime_sql_portable()
    _assert_validation_only_contract()
    _assert_alembic_authority()
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
