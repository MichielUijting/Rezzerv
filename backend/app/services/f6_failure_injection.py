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
    sql = " ".join(str(clauseelement or "").strip().upper().split())
    if not sql.startswith("UPDATE PURCHASE_IMPORT_BATCHES"):
        return False
    if "PROCESSING_STATUS" not in sql or "PROCESSED_AT" not in sql:
        return False

    for mapping in _parameter_mappings(multiparams, params):
        processing_status = str(mapping.get("processing_status") or "").strip().lower()
        if processing_status in {"processed", "partially_processed"} and mapping.get("batch_id") is not None:
            return True
    return False


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
