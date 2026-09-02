"""PostgreSQL runtime contract for legacy 0/1 boolean SQL.

The SQLite -> PostgreSQL foundation deliberately migrated a small, explicit set
of integer-backed boolean columns to native PostgreSQL BOOLEAN.  Some older raw
SQL call sites still express those columns with SQLite-style 0/1 literals.  This
module normalizes only that proven migration set at the SQLAlchemy boundary so a
stale call site cannot make a PostgreSQL request fail while the source-level
cleanup is completed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


MIGRATED_BOOLEAN_COLUMNS = frozenset(
    {
        "member_allowed",
        "is_primary",
        "is_auto_prefilled",
        "is_active",
        "is_deleted",
        "is_validated",
        "totals_overridden",
        "active",
    }
)

# Parameter names used by the remaining raw-SQL write paths for the explicit
# migration set.  Table/statement guards below keep generic names such as
# ``value`` from being coerced outside the relevant write path.
_STATEMENT_PARAMETER_RULES = (
    ("receipt_table_lines", ("is_deleted", "is_validated", "validated")),
    ("receipt_tables", ("totals_overridden",)),
    ("receipt_sources", ("is_active",)),
    ("product_identities", ("is_primary",)),
    ("purchase_import_lines", ("is_auto_prefilled", "can_auto_fill")),
    ("household_permission_policies", ("member_allowed", "value")),
    ("spaces", ("active",)),
    ("sublocations", ("active",)),
)


def _qualified_column_pattern(column: str) -> str:
    return rf"(?:(?:\b[a-zA-Z_][a-zA-Z0-9_]*\.)?\b{re.escape(column)}\b)"


def normalize_postgresql_boolean_statement(statement: str) -> str:
    """Translate SQLite-style boolean literals for explicitly migrated columns."""

    normalized = str(statement)
    for column in sorted(MIGRATED_BOOLEAN_COLUMNS, key=len, reverse=True):
        qualified = _qualified_column_pattern(column)
        normalized = re.sub(
            rf"COALESCE\(\s*({qualified})\s*,\s*0\s*\)",
            r"COALESCE(\1, FALSE)",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"({qualified})\s*=\s*0\b",
            r"\1 = FALSE",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"({qualified})\s*=\s*1\b",
            r"\1 = TRUE",
            normalized,
            flags=re.IGNORECASE,
        )

    # One historical purchase-import update encoded a boolean assignment as a
    # CASE around a 0/1 parameter. Once the parameter is a Python bool, the
    # direct assignment is the PostgreSQL-native equivalent.
    normalized = re.sub(
        r"(\bis_auto_prefilled\s*=\s*)CASE\s+WHEN\s+([^\s,]+)\s*=\s*1\s+THEN\s+1\s+ELSE\s+0\s+END",
        r"\1\2",
        normalized,
        flags=re.IGNORECASE,
    )

    # Normalize simple INSERT ... (columns) VALUES (...) literal pairs. This
    # covers legacy receipt-line inserts that still put literal 0/1 directly
    # into is_deleted/is_validated rather than using a bind parameter.
    normalized = _normalize_simple_insert_boolean_literals(normalized)
    return normalized


def _split_sql_list(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(value):
        char = value[index]
        if char == "'":
            if in_single_quote and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote:
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


def _normalize_simple_insert_boolean_literals(statement: str) -> str:
    pattern = re.compile(
        r"(?P<prefix>\bINSERT\s+INTO\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\()"
        r"(?P<columns>[^)]*)"
        r"(?P<middle>\)\s*VALUES\s*\()"
        r"(?P<values>[^;]*?)"
        r"(?P<suffix>\)(?:\s*(?:ON\s+CONFLICT|RETURNING)\b|\s*;|\s*$))",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        columns = _split_sql_list(match.group("columns"))
        values = _split_sql_list(match.group("values"))
        if len(columns) != len(values):
            return match.group(0)
        changed = False
        for index, raw_column in enumerate(columns):
            column = raw_column.strip().strip('"').split(".")[-1].lower()
            if column not in MIGRATED_BOOLEAN_COLUMNS:
                continue
            literal = values[index].strip()
            if literal == "0":
                values[index] = "FALSE"
                changed = True
            elif literal == "1":
                values[index] = "TRUE"
                changed = True
        if not changed:
            return match.group(0)
        return (
            match.group("prefix")
            + match.group("columns")
            + match.group("middle")
            + ", ".join(values)
            + match.group("suffix")
        )

    return pattern.sub(replace, statement)


def _coerce_parameter_mapping(statement: str, values: Mapping[str, Any]) -> dict[str, Any]:
    coerced = dict(values)
    lowered = statement.lower()
    for table_name, parameter_names in _STATEMENT_PARAMETER_RULES:
        if table_name not in lowered:
            continue
        for name in parameter_names:
            if name in coerced and coerced[name] is not None:
                coerced[name] = bool(coerced[name])
    return coerced


def normalize_postgresql_boolean_parameters(
    statement: str,
    multiparams: Any,
    params: Any,
) -> tuple[Any, Any]:
    """Return parameter containers with migrated boolean writes as Python bools."""

    normalized_params = (
        _coerce_parameter_mapping(statement, params)
        if isinstance(params, Mapping) and params
        else params
    )
    if multiparams:
        normalized_multi = tuple(
            _coerce_parameter_mapping(statement, item) if isinstance(item, Mapping) else item
            for item in multiparams
        )
    else:
        normalized_multi = multiparams
    return normalized_multi, normalized_params


def enforce_postgresql_boolean_parameters_before_execute(
    conn: Any,
    clauseelement: Any,
    multiparams: Any,
    params: Any,
    execution_options: Any,
):
    """SQLAlchemy before_execute hook: coerce proven boolean write parameters."""

    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        return clauseelement, multiparams, params
    statement = str(clauseelement)
    normalized_multi, normalized_params = normalize_postgresql_boolean_parameters(
        statement, multiparams, params
    )
    return clauseelement, normalized_multi, normalized_params


def enforce_postgresql_boolean_sql_before_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
):
    """SQLAlchemy before_cursor_execute hook: normalize stale 0/1 SQL literals."""

    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        return statement, parameters
    return normalize_postgresql_boolean_statement(statement), parameters
