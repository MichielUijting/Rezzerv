from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = BACKEND_ROOT / "app" / "api" / "catalog_routes.py"
OFF_LINK_PATH = BACKEND_ROOT / "app" / "services" / "off_product_link_service.py"

FORBIDDEN_SQL_PATTERNS = {
    "runtime CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "runtime CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "runtime ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "runtime DROP schema object": re.compile(
        r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE
    ),
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


def _assert_no_runtime_ddl() -> None:
    failures: list[str] = []
    for path in (CATALOG_PATH, OFF_LINK_PATH):
        source = path.read_text(encoding="utf-8-sig")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")
    if failures:
        raise AssertionError(
            "Catalog/OFF request paths contain runtime schema DDL:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_CATALOG_OFF_RUNTIME_DDL_ABSENT_GREEN")


def _assert_catalog_sql_portable() -> None:
    source = CATALOG_PATH.read_text(encoding="utf-8-sig")
    forbidden = {
        "SQLite COLLATE NOCASE": "COLLATE NOCASE",
        "SQLite datetime() receipt ordering": "datetime(pib.created_at)",
        "integer Boolean COALESCE": "COALESCE(is_primary, 0)",
    }
    present = [label for label, token in forbidden.items() if token in source]
    if present:
        raise AssertionError(f"Catalog SQL still contains non-portable constructs: {present}")

    required = (
        'sort_by in {"name", "brand", "primary_gtin", "product_type", "source"}',
        "LOWER({order_expression})",
        "COALESCE(is_primary, FALSE)",
        "ORDER BY pib.created_at DESC, pil.id DESC",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"Catalog PostgreSQL portability contract incomplete: {missing}")

    print("POSTGRESQL_CATALOG_CASE_INSENSITIVE_SORT_GREEN")
    print("POSTGRESQL_CATALOG_IDENTITY_BOOLEAN_READ_GREEN")
    print("POSTGRESQL_CATALOG_RECEIPT_TIMESTAMP_ORDER_GREEN")


def _assert_off_identity_boolean_bind() -> None:
    source = OFF_LINK_PATH.read_text(encoding="utf-8-sig")
    forbidden = (
        "is_primary = 1",
        "1.0, 1, CURRENT_TIMESTAMP",
    )
    present = [token for token in forbidden if token in source]
    if present:
        raise AssertionError(f"OFF identity DML still uses integer Boolean literals: {present}")

    required = (
        "is_primary = :is_primary",
        "1.0, :is_primary, CURRENT_TIMESTAMP",
        '"is_primary": True',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"OFF identity Boolean bind contract incomplete: {missing}")

    print("POSTGRESQL_OFF_IDENTITY_BOOLEAN_BIND_GREEN")


def main() -> None:
    for path in (CATALOG_PATH, OFF_LINK_PATH):
        if not path.is_file():
            raise AssertionError(f"Catalog/OFF scope file ontbreekt: {path}")
    _assert_no_runtime_ddl()
    _assert_catalog_sql_portable()
    _assert_off_identity_boolean_bind()
    print("POSTGRESQL_CATALOG_OFF_REQUEST_PORTABILITY_STATIC_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
