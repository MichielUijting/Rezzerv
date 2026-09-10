"""Test-only SQL failure injection for Fase 6 recovery authority.

The hook is dormant unless REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION=1.
When enabled on PostgreSQL, a mutating SQL execution whose bound parameters
contain F6_SQL_FAILURE_SENTINEL raises before the matching statement reaches
the driver. Read-only proof queries are never intercepted.

Because application mutations run inside engine.begin(), earlier writes in the
same transaction must be rolled back by SQLAlchemy/PostgreSQL.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

F6_SQL_FAILURE_SENTINEL = "F6-01-CONTROLLED-500"
F6_SQL_FAILURE_ENV = "REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION"
_MUTATING_SQL_PREFIXES = ("INSERT", "UPDATE", "DELETE")


def _enabled() -> bool:
    return str(os.getenv(F6_SQL_FAILURE_ENV, "") or "").strip().lower() in {"1", "true", "yes", "on"}


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


def inject_f6_controlled_failure_before_execute(conn, clauseelement, multiparams, params, execution_options):
    """Raise a deterministic test-only failure for a sentinel-bearing SQL write."""

    if not _enabled() or getattr(conn.dialect, "name", "") != "postgresql":
        return clauseelement, multiparams, params
    if not _is_mutating_statement(clauseelement):
        return clauseelement, multiparams, params

    if _contains_sentinel(params) or _contains_sentinel(multiparams):
        raise RuntimeError("F6-01 controlled PostgreSQL failure injection")

    return clauseelement, multiparams, params
