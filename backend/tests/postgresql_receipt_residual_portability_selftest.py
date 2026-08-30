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
    / "20260829_15_receipt_store_chain_schema_authority.py"
)
SCOPE_FILES = (
    "receipt_inventory_lifecycle_service.py",
    "receipt_status_sync.py",
    "receipt_reimport_lineage_service.py",
    "receipt_source_helper_service.py",
    "receipt_status_baseline_service.py",
    "receipt_status_baseline_service/__init__.py",
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "SQLite datetime()": re.compile(r"\bdatetime\s*\(", re.IGNORECASE),
    "SQLite instr()": re.compile(r"\binstr\s*\(", re.IGNORECASE),
}


def _scope_paths() -> tuple[Path, ...]:
    paths = tuple(SERVICE_ROOT / filename for filename in SCOPE_FILES)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"Receipt residual scope files ontbreken: {missing}")
    if not MIGRATION_PATH.is_file():
        raise AssertionError(f"Receipt store-chain Alembic authority ontbreekt: {MIGRATION_PATH}")
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
            "Receipt residual runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_RECEIPT_RESIDUAL_SQL_PORTABLE_GREEN")
    print("POSTGRESQL_RECEIPT_RESIDUAL_RUNTIME_DDL_ABSENT_GREEN")


def _assert_boolean_contract() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in _scope_paths()
    )
    forbidden = (
        "COALESCE(rtl.is_deleted, 0)",
        "COALESCE(rtl_count.is_deleted, 0)",
        "COALESCE(is_validated, 0)",
        "is_active = 1",
        "is_active)\n                    VALUES (:id, :household_id, 'email', :label, :source_path, 1)",
        "is_active)\n                    VALUES (:id, :household_id, 'gmail_label', :label, :source_path, 1)",
    )
    present = [token for token in forbidden if token in combined]
    if present:
        raise AssertionError(f"Receipt runtime still assumes integer PostgreSQL Booleans: {present}")
    required = (
        "COALESCE(rtl.is_deleted, FALSE) IS FALSE",
        "COALESCE(is_validated, FALSE)",
        "is_active = TRUE",
    )
    missing = [token for token in required if token not in combined]
    if missing:
        raise AssertionError(f"Receipt native Boolean contract incomplete: {missing}")
    print("POSTGRESQL_RECEIPT_RESIDUAL_BOOLEAN_SQL_GREEN")


def _assert_store_chain_alembic_authority() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8-sig")
    required_migration_tokens = (
        'revision: str = "20260829_15"',
        'down_revision: Union[str, None] = "20260829_14"',
        '_RECEIPT_TABLE = "receipt_tables"',
        '"store_chain" not in columns',
        'sa.Column("store_chain", sa.Text(), nullable=True)',
        "op.add_column(",
    )
    missing_migration = [
        token for token in required_migration_tokens if token not in migration_source
    ]
    if missing_migration:
        raise AssertionError(
            f"Receipt store-chain Alembic authority incomplete: {missing_migration}"
        )

    status_sources = (
        SERVICE_ROOT / "receipt_status_baseline_service.py",
        SERVICE_ROOT / "receipt_status_baseline_service" / "__init__.py",
    )
    for status_path in status_sources:
        status_source = status_path.read_text(encoding="utf-8-sig")
        if "inspect(conn).get_columns(table_name)" not in status_source:
            raise AssertionError(
                f"Receipt status baseline does not use portable schema inspection: {status_path}"
            )
        if "Canonical receipt_tables.store_chain schema ontbreekt" not in status_source:
            raise AssertionError(
                f"Receipt status baseline is not fail-closed on missing store_chain: {status_path}"
            )
        if "ALTER TABLE receipt_tables ADD COLUMN store_chain" in status_source:
            raise AssertionError(
                f"Receipt status baseline still owns store_chain DDL at runtime: {status_path}"
            )

    print("POSTGRESQL_RECEIPT_STORE_CHAIN_ALEMBIC_AUTHORITY_GREEN")
    print("POSTGRESQL_RECEIPT_STATUS_VALIDATION_ONLY_GREEN")


def main() -> None:
    scope = _scope_paths()
    print(f"POSTGRESQL_RECEIPT_RESIDUAL_SCOPE_GREEN service_files={len(scope)}")
    _assert_runtime_sql_portable()
    _assert_boolean_contract()
    _assert_store_chain_alembic_authority()
    print("POSTGRESQL_RECEIPT_RESIDUAL_STATIC_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
