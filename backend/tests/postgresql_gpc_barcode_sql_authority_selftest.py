from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = BACKEND_ROOT / "app" / "services"
MIGRATION = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260829_08_gpc_barcode_catalog_authority.py"
)

SCOPE_FILES = (
    "gpc_catalog_service.py",
    "gpc_local_catalog_service.py",
    "barcode_identity_service.py",
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "CREATE TRIGGER": re.compile(r"\bCREATE\s+TRIGGER\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP": re.compile(r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE),
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
        raise AssertionError(f"PR2i static gate scope files ontbreken: {missing}")
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
        source = path.read_text(encoding="utf-8")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")

            if re.search(
                r"COALESCE\s*\(\s*(?:\w+\.)?is_primary\s*,\s*[01]\s*\)",
                sql,
                re.IGNORECASE,
            ):
                failures.append(
                    f"{path.name}: SQL#{index}: integer COALESCE fallback for BOOLEAN is_primary"
                )
            if re.search(
                r"\bis_primary\s*=\s*[01]\b",
                sql,
                re.IGNORECASE,
            ):
                failures.append(
                    f"{path.name}: SQL#{index}: integer assignment/comparison for BOOLEAN is_primary"
                )
            if re.search(
                r"THEN\s+[01]\s+ELSE\s+is_primary\b",
                sql,
                re.IGNORECASE,
            ):
                failures.append(
                    f"{path.name}: SQL#{index}: integer CASE result for BOOLEAN is_primary"
                )
            if path.name == "gpc_local_catalog_service.py" and re.search(
                r"COALESCE\s*\(\s*active\s*,\s*[01]\s*\)\s*=\s*1",
                sql,
                re.IGNORECASE,
            ):
                failures.append(
                    f"{path.name}: SQL#{index}: integer boolean assumption for gpc_product_groups.active"
                )

    if failures:
        raise AssertionError(
            "PR2i GPC/barcode runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_GPC_BARCODE_SQL_PORTABLE_GREEN")


def _assert_runtime_schema_authority_absent() -> None:
    failures: list[str] = []
    for path in _scope_paths():
        source = path.read_text(encoding="utf-8")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
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
            "PR2i GPC/barcode request paths still own runtime schema mutations: "
            + ", ".join(sorted(failures))
        )
    print("POSTGRESQL_GPC_BARCODE_RUNTIME_DDL_ABSENT_GREEN")


def _assert_validation_only_ensure_contract() -> None:
    catalog = (SERVICE_ROOT / "gpc_catalog_service.py").read_text(encoding="utf-8")
    local = (SERVICE_ROOT / "gpc_local_catalog_service.py").read_text(encoding="utf-8")
    required = (
        (catalog, "def ensure_gpc_catalog_schema"),
        (catalog, "inspect(db_engine)"),
        (local, "def ensure_local_gpc_schema"),
        (local, "inspect(engine)"),
    )
    missing = [token for source, token in required if token not in source]
    if missing:
        raise AssertionError(
            f"PR2i validation-only ensure contract incomplete: {missing}"
        )
    print("POSTGRESQL_GPC_BARCODE_VALIDATION_ONLY_ENSURE_GREEN")


def _assert_alembic_authority_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    required = (
        'revision: str = "20260829_08"',
        'down_revision: Union[str, None] = "20260829_07"',
        '"gpc_segments"',
        '"gpc_families"',
        '"gpc_classes"',
        '"gpc_bricks"',
        '"gpc_attribute_types"',
        '"gpc_attribute_values"',
        '"gpc_brick_attribute_types"',
        '"gpc_attribute_type_values"',
        '"gpc_import_runs"',
        '"gpc_product_groups"',
        '"gpc_family_code"',
        '"gpc_class_code"',
        '"gpc_brick_code"',
        '"idx_gpc_families_segment"',
        '"idx_gpc_classes_family"',
        '"idx_gpc_bricks_class"',
        "sa.Boolean()",
        "op.create_table",
        "op.create_index",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"PR2i Alembic authority contract incomplete: {missing}")
    print("POSTGRESQL_GPC_BARCODE_ALEMBIC_AUTHORITY_GREEN")


def main() -> None:
    scope = _scope_paths()
    if len(scope) != len(SCOPE_FILES):
        raise AssertionError("PR2i static gate resolved incomplete service scope")
    print(
        "POSTGRESQL_GPC_BARCODE_SCOPE_GREEN "
        f"service_files={len(scope)}"
    )
    _assert_runtime_sql_portable()
    _assert_runtime_schema_authority_absent()
    _assert_validation_only_ensure_contract()
    _assert_alembic_authority_contract()
    print("POSTGRESQL_GPC_BARCODE_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
