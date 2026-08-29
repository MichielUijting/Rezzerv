from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260829_11_gpc_assignment_translation_authority.py"
)
SCOPE_PATHS = (
    APP_ROOT / "api" / "catalog_gpc_routes.py",
    APP_ROOT / "services" / "gpc_article_assignment_service.py",
    APP_ROOT / "services" / "gpc_import_service.py",
    APP_ROOT / "services" / "gpc_translation_service.py",
)

FORBIDDEN = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
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


def _sql_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    values: list[str] = []
    for node in ast.walk(tree):
        value = _string_value(node)
        if value is None:
            continue
        if re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|PRAGMA)\b", value, re.IGNORECASE):
            values.append(value)
    return values


def _assert_runtime_sql_portable() -> None:
    failures: list[str] = []
    for path in SCOPE_PATHS:
        if not path.is_file():
            raise AssertionError(f"PR2l scope file ontbreekt: {path}")
        for index, sql in enumerate(_sql_literals(path.read_text(encoding="utf-8-sig")), start=1):
            for label, pattern in FORBIDDEN.items():
                if pattern.search(sql):
                    failures.append(f"{path.relative_to(BACKEND_ROOT)} SQL#{index}: {label}")
            normalized = " ".join(sql.lower().split())
            if "gpc_product_groups" in normalized and re.search(r"\bactive\s*=\s*1\b", normalized):
                failures.append(
                    f"{path.relative_to(BACKEND_ROOT)} SQL#{index}: gpc_product_groups Boolean active=1"
                )
    if failures:
        raise AssertionError(
            "Residual GPC runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_GPC_RESIDUAL_SQL_PORTABLE_GREEN")
    print("POSTGRESQL_GPC_RESIDUAL_RUNTIME_DDL_ABSENT_GREEN")


def _assert_validation_only_schema() -> None:
    required_tokens = {
        APP_ROOT / "api" / "catalog_gpc_routes.py": (
            "def _ensure_assignment_schema",
            "inspect(engine)",
            "idx_global_product_gpc_brick_code",
        ),
        APP_ROOT / "services" / "gpc_article_assignment_service.py": (
            "def _ensure_schema",
            "inspect(engine)",
        ),
        APP_ROOT / "services" / "gpc_import_service.py": (
            "def _ensure_gpc_schema",
            "inspect(conn)",
            "idx_gpc_product_groups_hierarchy",
            "active = TRUE",
        ),
        APP_ROOT / "services" / "gpc_translation_service.py": (
            "def ensure_gpc_translation_schema",
            "inspect(db_engine)",
            "idx_gpc_translation_language",
        ),
    }
    for path, tokens in required_tokens.items():
        source = path.read_text(encoding="utf-8-sig")
        missing = [token for token in tokens if token not in source]
        if missing:
            raise AssertionError(f"Validation-only contract incomplete for {path.name}: {missing}")
    print("POSTGRESQL_GPC_RESIDUAL_VALIDATION_ONLY_SCHEMA_GREEN")


def _assert_alembic_authority() -> None:
    if not MIGRATION_PATH.is_file():
        raise AssertionError(f"PR2l Alembic revision ontbreekt: {MIGRATION_PATH}")
    source = MIGRATION_PATH.read_text(encoding="utf-8-sig")
    required = (
        'revision: str = "20260829_11"',
        'down_revision: Union[str, None] = "20260829_10"',
        '"global_product_gpc_bricks"',
        '"global_product_gpc_migration_suppressions"',
        '"gpc_translations"',
        '"gpc_translation_import_runs"',
        'index_name="idx_gpc_product_groups_hierarchy"',
        'index_name="idx_gpc_translation_language"',
        'index_name="idx_global_product_gpc_brick_code"',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"PR2l Alembic authority contract incomplete: {missing}")
    print("POSTGRESQL_GPC_RESIDUAL_ALEMBIC_AUTHORITY_GREEN")


def main() -> None:
    print(f"POSTGRESQL_GPC_RESIDUAL_SCOPE_GREEN files={len(SCOPE_PATHS)}")
    _assert_runtime_sql_portable()
    _assert_validation_only_schema()
    _assert_alembic_authority()
    print("POSTGRESQL_GPC_RESIDUAL_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
