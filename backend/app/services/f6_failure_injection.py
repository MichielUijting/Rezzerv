"""Test-only SQL failure injection for Fase 6 recovery authority.

The hook is dormant unless REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION=1.
Inventory authority uses a sentinel-bearing mutation. Receipt authority can
additionally enable a narrowly scoped failure on the final successful
purchase-import batch UPDATE, after receipt/inventory writes have happened but
before the surrounding PostgreSQL transaction commits. Kassa review authority
can enable a separate narrowly scoped failure when approval is about to create
the receipt-backed Uitpakken batch; this occurs after the receipt approval
UPDATE but before commit, proving that PostgreSQL rolls the approval back.
Unpacking authority can enable the same final batch transaction boundary for
one explicit purchase-import batch, proving that line/event writes are rolled
back before a controlled HTTP 500 reaches the real UI.

F6-02 can additionally enable REZZERV_TEST_ONLY_F6_TEMPORARY_FAILURE_ONCE=1.
In that mode the configured authority fails exactly once per target in the
backend container and the next identical user action is allowed to continue.
The one-shot marker is created atomically in /tmp so retry behaviour remains
deterministic even if the application serves requests from more than one
process. Production defaults never enable these hooks.

Read-only proof queries are never intercepted.
"""
from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

F6_SQL_FAILURE_SENTINEL = "F6-01-CONTROLLED-500"
F6_SQL_FAILURE_ENV = "REZZERV_TEST_ONLY_F6_SQL_FAILURE_INJECTION"
F6_TEMPORARY_FAILURE_ONCE_ENV = "REZZERV_TEST_ONLY_F6_TEMPORARY_FAILURE_ONCE"
F6_RECEIPT_FINALIZATION_ENV = "REZZERV_TEST_ONLY_F6_RECEIPT_FINALIZATION_FAILURE"
F6_RECEIPT_FAILURE_MARKER = "F6-01-RECEIPT-CONTROLLED-500"
F6_RECEIPT_TEMPORARY_MARKER = "F6-02-RECEIPT-TEMPORARY-FAILURE"
F6_KASSA_APPROVAL_ENV = "REZZERV_TEST_ONLY_F6_KASSA_APPROVAL_FAILURE"
F6_KASSA_RECEIPT_ID_ENV = "REZZERV_TEST_ONLY_F6_KASSA_RECEIPT_ID"
F6_KASSA_FAILURE_MARKER = "F6-01-KASSA-CONTROLLED-500"
F6_KASSA_TEMPORARY_MARKER = "F6-02-KASSA-TEMPORARY-FAILURE"
F6_UNPACKING_FINALIZATION_ENV = "REZZERV_TEST_ONLY_F6_UNPACKING_FINALIZATION_FAILURE"
F6_UNPACKING_BATCH_ID_ENV = "REZZERV_TEST_ONLY_F6_UNPACKING_BATCH_ID"
F6_UNPACKING_FAILURE_MARKER = "F6-01-UNPACKING-CONTROLLED-500"
F6_UNPACKING_TEMPORARY_MARKER = "F6-02-UNPACKING-TEMPORARY-FAILURE"
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


def _temporary_failure_once_enabled() -> bool:
    return _enabled() and _truthy_env(F6_TEMPORARY_FAILURE_ONCE_ENV)


def _receipt_finalization_enabled() -> bool:
    return _enabled() and _truthy_env(F6_RECEIPT_FINALIZATION_ENV)


def _kassa_approval_enabled() -> bool:
    return (
        _enabled()
        and _truthy_env(F6_KASSA_APPROVAL_ENV)
        and bool(str(os.getenv(F6_KASSA_RECEIPT_ID_ENV, "") or "").strip())
    )


def _unpacking_finalization_enabled() -> bool:
    return (
        _enabled()
        and _truthy_env(F6_UNPACKING_FINALIZATION_ENV)
        and bool(str(os.getenv(F6_UNPACKING_BATCH_ID_ENV, "") or "").strip())
    )


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


def _parameter_value(name: str, multiparams: Any, params: Any) -> str:
    for mapping in _parameter_mappings(multiparams, params):
        value = str(mapping.get(name) or "").strip()
        if value:
            return value
    return ""


def _is_receipt_finalization_update(clauseelement: Any, multiparams: Any, params: Any) -> bool:
    """Match the final batch timestamp write, not the earlier status write."""

    sql_source = clauseelement if clauseelement is not None else ""
    sql = " ".join(str(sql_source).strip().upper().split())
    if sql != _RECEIPT_FINALIZATION_SQL:
        return False

    return any(mapping.get("id") is not None for mapping in _parameter_mappings(multiparams, params))


def _is_kassa_approval_unpack_batch_insert(clauseelement: Any, multiparams: Any, params: Any) -> bool:
    """Match only the receipt-backed Uitpakken batch for the configured F6 receipt."""

    sql_source = clauseelement if clauseelement is not None else ""
    sql = " ".join(str(sql_source).strip().upper().split())
    if not sql.startswith("INSERT INTO PURCHASE_IMPORT_BATCHES"):
        return False
    if "'RECEIPT'" not in sql:
        return False

    target_receipt_id = str(os.getenv(F6_KASSA_RECEIPT_ID_ENV, "") or "").strip()
    expected_source_reference = f"receipt:{target_receipt_id}"
    return any(
        str(mapping.get("source_reference") or "").strip() == expected_source_reference
        for mapping in _parameter_mappings(multiparams, params)
    )


def _is_unpacking_finalization_update(clauseelement: Any, multiparams: Any, params: Any) -> bool:
    """Match only the finalization UPDATE for the configured F6 Unpacking batch."""

    if not _is_receipt_finalization_update(clauseelement, multiparams, params):
        return False
    target_batch_id = str(os.getenv(F6_UNPACKING_BATCH_ID_ENV, "") or "").strip()
    return any(
        str(mapping.get("id") or "").strip() == target_batch_id
        for mapping in _parameter_mappings(multiparams, params)
    )


def _one_shot_marker_path(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"/tmp/rezzerv-f6-temporary-{digest}.marker"


def _should_inject_now(key: str) -> bool:
    """Return True always for F6-01, exactly once per key for F6-02."""

    if not _temporary_failure_once_enabled():
        return True
    marker_path = _one_shot_marker_path(key)
    try:
        fd = os.open(marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write(key + "\n")
    return True


def _raise_failure(
    *,
    key: str,
    controlled_marker: str,
    temporary_marker: str,
    controlled_log_message: str,
    controlled_message: str,
    temporary_message: str,
) -> bool:
    if not _should_inject_now(key):
        return False
    if _temporary_failure_once_enabled():
        print(f"{temporary_marker}: injected one-shot temporary failure", flush=True)
        raise RuntimeError(temporary_message)
    print(f"{controlled_marker}: {controlled_log_message}", flush=True)
    raise RuntimeError(controlled_message)


def inject_f6_controlled_failure_before_execute(conn, clauseelement, multiparams, params, execution_options):
    """Raise deterministic test-only failures at production transaction boundaries."""

    if not _enabled() or getattr(conn.dialect, "name", "") != "postgresql":
        return clauseelement, multiparams, params
    if not _is_mutating_statement(clauseelement):
        return clauseelement, multiparams, params

    if _kassa_approval_enabled() and _is_kassa_approval_unpack_batch_insert(clauseelement, multiparams, params):
        target_receipt_id = str(os.getenv(F6_KASSA_RECEIPT_ID_ENV, "") or "").strip()
        _raise_failure(
            key=f"kassa:{target_receipt_id}",
            controlled_marker=F6_KASSA_FAILURE_MARKER,
            temporary_marker=F6_KASSA_TEMPORARY_MARKER,
            controlled_log_message="injected controlled Kassa approval failure",
            controlled_message="F6 controlled Kassa approval failure",
            temporary_message="F6 temporary Kassa approval failure",
        )
        return clauseelement, multiparams, params

    if _unpacking_finalization_enabled() and _is_unpacking_finalization_update(clauseelement, multiparams, params):
        target_batch_id = str(os.getenv(F6_UNPACKING_BATCH_ID_ENV, "") or "").strip()
        _raise_failure(
            key=f"unpacking:{target_batch_id}",
            controlled_marker=F6_UNPACKING_FAILURE_MARKER,
            temporary_marker=F6_UNPACKING_TEMPORARY_MARKER,
            controlled_log_message="injected controlled Unpacking finalization failure",
            controlled_message="F6 controlled Unpacking finalization failure",
            temporary_message="F6 temporary Unpacking finalization failure",
        )
        return clauseelement, multiparams, params

    if _receipt_finalization_enabled() and _is_receipt_finalization_update(clauseelement, multiparams, params):
        batch_id = _parameter_value("id", multiparams, params)
        _raise_failure(
            key=f"receipt:{batch_id}",
            controlled_marker=F6_RECEIPT_FAILURE_MARKER,
            temporary_marker=F6_RECEIPT_TEMPORARY_MARKER,
            controlled_log_message="injected controlled receipt finalization failure",
            controlled_message="F6 controlled receipt finalization failure",
            temporary_message="F6 temporary receipt finalization failure",
        )
        return clauseelement, multiparams, params

    if _contains_sentinel(params) or _contains_sentinel(multiparams):
        raise RuntimeError("F6-01 controlled PostgreSQL failure injection")

    return clauseelement, multiparams, params
