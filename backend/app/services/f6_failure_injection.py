"""Test-only SQL failure injection for Fase 6 recovery authority.

The hook is dormant unless REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION=1.
Inventory authority uses a sentinel-bearing mutation. Receipt authority can
additionally enable a narrowly scoped failure on the final successful
purchase-import batch UPDATE, after receipt/inventory writes have happened but
before the surrounding PostgreSQL transaction commits.

Read-only proof queries are never intercepted. Production defaults never enable
these hooks.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

F6_SQL_FAILURE_SENTINEL = "F6-01-CONTROLLED-500"
F6_SQL_FAILURE_ENV = "REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION"
F6_RECEIPT_FINALIZATION_ENV = "REZZERV_TEST_ONLY_F6_RECEIPT_FINALIZATION_FAILURE"
F6_RECEIPT_FAILURE_MARKER = "F6-01-RECEIPT-CONTROLLED-500"
_MUTATING_SQL_PREFIXES = ("INSERT", "UPDATE", "DELETE")
_RECEIPT_FINALIZATION_SQL = (
    "UPDATE PURCHASE_IMPORT_BATCHES "
    "SET PROCESSED_AT = CURRENT_TIMESTAMP "
    "WHERE ID = :ID"
)


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    return _truthy_env(F6_SQL_FAILURE_ENV)


def _receipt_finalization_enabled() -> bool:
    return _enabled() and _truthy_env(F6_RECEIPT_FINALIZATION_ENV)


def _contains_sentinel(value: Any) -> bool:
    if isinstance(value, str):
        return value == F6_SQL_FAILURE_SENTINEL
    if isinstance(value, Mapping):
        return any(_contains_sentinel(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_sentinel(item) for item in value)
    return False


def _is_mutating_statement(clauseelement: Any) -> bool:
    sql = str(clauseelement) if clauseelement is not None else ""
    return sql.lstrip().upper().startswith(_MUTATING_SQL_PREFIXES)


def _parameter_mappings(multiparams: Any, params: Any):
    if isinstance(params, Mapping):
        yield params
    if isinstance(multiparams, Mapping):
        yield multiparams
    elif isinstance(multiparams, (list, tuple)):
        for item in multiparams:
            if isinstance(item, Mapping):
                yield item


def _is_receipt_finalization_update(clauseelement: Any, multiparams: Any, params: Any) -> bool:
    """Match the final batch timestamp write, not the earlier status write.

    Production first updates ``import_status`` and only after successful line
    processing writes ``processed_at``. That second UPDATE is the stable point
    after inventory/event mutations and immediately before transaction commit.
    """

    sql_source = clauseelement if clauseelement is not None else ""
    sql = " ".join(str(sql_source).strip().upper().split())
    if sql != _RECEIPT_FINALIZATION_SQL:
        return False

    return any(mapping.get("id") is not None for mapping in _parameter_mappings(multiparams, params))


def inject_f6_controlled_failure_before_execute(conn, clauseelement, multiparams, params, execution_options):
    """Raise deterministic test-only failures at production transaction boundaries."""

    if not _enabled() or getattr(conn.dialect, "name", "") != "postgresql":
        return clauseelement, multiparams, params
    if not _is_mutating_statement(clauseelement):
        return clauseelement, multiparams, params

    if _receipt_finalization_enabled() and _is_receipt_finalization_update(clauseelement, multiparams, params):
        print(f"{F6_RECEIPT_FAILURE_MARKER}: injected controlled receipt finalization failure", flush=True)
        raise RuntimeError("F6 controlled receipt finalization failure")

    if _contains_sentinel(params) or _contains_sentinel(multiparams):
        raise RuntimeError("F6-01 controlled PostgreSQL failure injection")

    return clauseelement, multiparams, params
