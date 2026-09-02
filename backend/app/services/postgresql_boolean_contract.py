"""PostgreSQL runtime contract for legacy 0/1 boolean SQL.

The SQLite -> PostgreSQL migration converted the explicit table/column set
below to native BOOLEAN. Older raw SQL still contains some 0/1 expressions for
those columns. Only statements that reference the proven table are normalized.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import String, bindparam


MIGRATED_BOOLEAN_COLUMNS_BY_TABLE = {
    "household_permission_policies": frozenset({"member_allowed"}),
    "product_identities": frozenset({"is_primary"}),
    "purchase_import_lines": frozenset({"is_auto_prefilled"}),
    "receipt_sources": frozenset({"is_active"}),
    "receipt_table_lines": frozenset({"is_deleted", "is_validated"}),
    "receipt_tables": frozenset({"totals_overridden"}),
    "spaces": frozenset({"active"}),
    "sublocations": frozenset({"active"}),
}

_STATEMENT_PARAMETER_RULES = {
    "receipt_table_lines": ("is_deleted", "is_validated", "validated"),
    "receipt_tables": ("totals_overridden",),
    "receipt_sources": ("is_active",),
    "product_identities": ("is_primary",),
    "purchase_import_lines": ("is_auto_prefilled", "can_auto_fill"),
    "household_permission_policies": ("member_allowed", "value"),
    "spaces": ("active",),
    "sublocations": ("active",),
}

_RECEIPT_LINE_NULLABLE_STRING_PARAMETER = "matched_household_article_id"


def _tables_in_statement(statement: str) -> set[str]:
    lowered = statement.lower()
    return {table for table in MIGRATED_BOOLEAN_COLUMNS_BY_TABLE if re.search(rf"\b{re.escape(table)}\b", lowered)}


def _qualified_column_pattern(column: str) -> str:
    return rf"(?:(?:\b[a-zA-Z_][a-zA-Z0-9_]*\.)?\b{re.escape(column)}\b)"


def _split_sql_list(value: str) -> list[str]:
    parts, start, depth, quoted = [], 0, 0, False
    index = 0
    while index < len(value):
        char = value[index]
        if char == "'":
            if quoted and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(value[start:index].strip())
                start = index + 1
        index += 1
    parts.append(value[start:].strip())
    return parts


def _normalize_simple_insert_boolean_literals(statement: str, active_tables: set[str]) -> str:
    pattern = re.compile(
        r"(?P<prefix>\bINSERT\s+INTO\s+(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s*\()"
        r"(?P<columns>[^)]*)(?P<middle>\)\s*VALUES\s*\()"
        r"(?P<values>[^;]*?)(?P<suffix>\)(?:\s*(?:ON\s+CONFLICT|RETURNING)\b|\s*;|\s*$))",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        table = match.group("table").lower()
        if table not in active_tables:
            return match.group(0)
        boolean_columns = MIGRATED_BOOLEAN_COLUMNS_BY_TABLE[table]
        columns = _split_sql_list(match.group("columns"))
        values = _split_sql_list(match.group("values"))
        if len(columns) != len(values):
            return match.group(0)
        changed = False
        for index, raw_column in enumerate(columns):
            column = raw_column.strip().strip('"').split(".")[-1].lower()
            if column not in boolean_columns:
                continue
            literal = values[index].strip()
            if literal in {"0", "1"}:
                values[index] = "FALSE" if literal == "0" else "TRUE"
                changed = True
        if not changed:
            return match.group(0)
        return match.group("prefix") + match.group("columns") + match.group("middle") + ", ".join(values) + match.group("suffix")

    return pattern.sub(replace, statement)


def _normalize_boolean_parameter_comparisons(statement: str, active_tables: set[str]) -> str:
    normalized = statement
    for table in active_tables:
        for name in _STATEMENT_PARAMETER_RULES[table]:
            escaped_name = re.escape(name)
            placeholder = rf"(?P<param>%\({escaped_name}\)s|:{escaped_name}\b)"
            normalized = re.sub(
                rf"{placeholder}\s*=\s*1\b",
                r"\g<param>",
                normalized,
                flags=re.IGNORECASE,
            )
            normalized = re.sub(
                rf"{placeholder}\s*=\s*0\b",
                r"(NOT \g<param>)",
                normalized,
                flags=re.IGNORECASE,
            )
    return normalized


def normalize_postgresql_boolean_statement(statement: str) -> str:
    normalized = str(statement)
    active_tables = _tables_in_statement(normalized)
    for table in active_tables:
        for column in MIGRATED_BOOLEAN_COLUMNS_BY_TABLE[table]:
            qualified = _qualified_column_pattern(column)
            normalized = re.sub(rf"COALESCE\(\s*({qualified})\s*,\s*0\s*\)", r"COALESCE(\1, FALSE)", normalized, flags=re.IGNORECASE)
            normalized = re.sub(rf"({qualified})\s*=\s*0\b", r"\1 = FALSE", normalized, flags=re.IGNORECASE)
            normalized = re.sub(rf"({qualified})\s*=\s*1\b", r"\1 = TRUE", normalized, flags=re.IGNORECASE)

    if "purchase_import_lines" in active_tables:
        normalized = re.sub(
            r"(\bis_auto_prefilled\s*=\s*)CASE\s+WHEN\s+([^\s,]+)\s*=\s*1\s+THEN\s+1\s+ELSE\s+0\s+END",
            r"\1\2",
            normalized,
            flags=re.IGNORECASE,
        )
    normalized = _normalize_boolean_parameter_comparisons(normalized, active_tables)
    return _normalize_simple_insert_boolean_literals(normalized, active_tables)


def _coerce_parameter_mapping(statement: str, values: Mapping[str, Any]) -> dict[str, Any]:
    coerced = dict(values)
    for table in _tables_in_statement(statement):
        for name in _STATEMENT_PARAMETER_RULES[table]:
            if name in coerced and coerced[name] is not None:
                coerced[name] = bool(coerced[name])
    return coerced


def normalize_postgresql_boolean_parameters(statement: str, multiparams: Any, params: Any) -> tuple[Any, Any]:
    normalized_params = _coerce_parameter_mapping(statement, params) if isinstance(params, Mapping) and params else params
    normalized_multi = tuple(_coerce_parameter_mapping(statement, item) if isinstance(item, Mapping) else item for item in multiparams) if multiparams else multiparams
    return normalized_multi, normalized_params


def _bind_receipt_line_nullable_string_parameter(clauseelement: Any) -> Any:
    statement = str(clauseelement)
    if "receipt_table_lines" not in _tables_in_statement(statement):
        return clauseelement
    bindparams = getattr(clauseelement, "_bindparams", {})
    bind_parameter_types = getattr(clauseelement, "bindparams", None)
    if (
        _RECEIPT_LINE_NULLABLE_STRING_PARAMETER not in bindparams
        or not callable(bind_parameter_types)
    ):
        return clauseelement
    return bind_parameter_types(
        bindparam(_RECEIPT_LINE_NULLABLE_STRING_PARAMETER, type_=String())
    )


def enforce_postgresql_boolean_parameters_before_execute(conn: Any, clauseelement: Any, multiparams: Any, params: Any, execution_options: Any):
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        return clauseelement, multiparams, params
    typed_clauseelement = _bind_receipt_line_nullable_string_parameter(clauseelement)
    normalized_multi, normalized_params = normalize_postgresql_boolean_parameters(str(typed_clauseelement), multiparams, params)
    return typed_clauseelement, normalized_multi, normalized_params


def enforce_postgresql_boolean_sql_before_cursor_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool):
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        return statement, parameters
    return normalize_postgresql_boolean_statement(statement), parameters
