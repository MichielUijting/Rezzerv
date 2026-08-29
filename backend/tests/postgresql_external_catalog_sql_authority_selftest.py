from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = BACKEND_ROOT / "app" / "services"
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "20260829_07_external_catalog_request_authority.py"

EXTRA_SCOPE = (
    "open_food_facts_candidate_store.py",
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "CREATE TRIGGER": re.compile(r"\bCREATE\s+TRIGGER\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP": re.compile(r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "rowid": re.compile(r"\browid\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
    "SQLite datetime()": re.compile(r"\bdatetime\s*\(", re.IGNORECASE),
}

BOOLEAN_COLUMNS = (
    "is_probable",
    "is_user_confirmed",
    "is_external_database_override",
    "is_primary",
)


def _scope_paths() -> tuple[Path, ...]:
    paths = {path for path in SERVICE_ROOT.glob("external_*.py") if path.is_file()}
    paths.update(SERVICE_ROOT / filename for filename in EXTRA_SCOPE)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"PR2h static gate scope files ontbreken: {sorted(missing)}")
    return tuple(sorted(paths, key=lambda path: path.name))


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
        source = path.read_text(encoding="utf-8")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")
            for column in BOOLEAN_COLUMNS:
                if re.search(rf"\b{re.escape(column)}\s*=\s*[01]\b", sql, re.IGNORECASE):
                    failures.append(
                        f"{path.name}: SQL#{index}: integer comparison against BOOLEAN {column}"
                    )
                if re.search(
                    rf"COALESCE\s*\(\s*{re.escape(column)}\s*,\s*[01]\s*\)",
                    sql,
                    re.IGNORECASE,
                ):
                    failures.append(
                        f"{path.name}: SQL#{index}: integer COALESCE fallback for BOOLEAN {column}"
                    )
    if failures:
        raise AssertionError(
            "PR2h external catalog/link runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_EXTERNAL_CATALOG_SQL_PORTABLE_GREEN")


def _assert_runtime_schema_authority_absent() -> None:
    failures: list[str] = []
    for path in _scope_paths():
        source = path.read_text(encoding="utf-8")
        sql_literals = _text_sql_literals(source)
        for index, sql in enumerate(sql_literals, start=1):
            normalized = " ".join(sql.upper().split())
            if any(
                token in normalized
                for token in (
                    "CREATE TABLE",
                    "CREATE INDEX",
                    "CREATE UNIQUE INDEX",
                    "CREATE TRIGGER",
                    "ALTER TABLE",
                    "DROP TABLE",
                    "DROP INDEX",
                    "DROP TRIGGER",
                )
            ):
                failures.append(f"{path.name}: SQL#{index}")
    if failures:
        raise AssertionError(
            "PR2h request paths still own runtime schema mutations: "
            + ", ".join(sorted(failures))
        )
    print("POSTGRESQL_EXTERNAL_CATALOG_RUNTIME_DDL_ABSENT_GREEN")


def _assert_alembic_authority_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    required = (
        'revision: str = "20260829_07"',
        'down_revision: Union[str, None] = "20260829_06"',
        '"external_product_candidates"',
        '"external_product_index"',
        '"external_relation_batch_decisions"',
        "op.create_table",
        "op.create_index",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"PR2h Alembic authority contract incomplete: {missing}")
    print("POSTGRESQL_EXTERNAL_CATALOG_ALEMBIC_AUTHORITY_GREEN")


def main() -> None:
    scope = _scope_paths()
    if not scope:
        raise AssertionError("PR2h static gate resolved an empty external service scope")
    print(
        "POSTGRESQL_EXTERNAL_CATALOG_SCOPE_GREEN "
        f"service_files={len(scope)}"
    )
    _assert_runtime_sql_portable()
    _assert_runtime_schema_authority_absent()
    _assert_alembic_authority_contract()
    print("POSTGRESQL_EXTERNAL_CATALOG_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
