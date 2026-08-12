"""Minimal receipt lifecycle foundation for safe delete/reimport semantics.

Release A deliberately extends existing receipt entities instead of introducing
parallel identity or processing tables. Persisted facts keep one source of truth:

- receipt_tables: current receipt workflow + stable logical receipt identity
- receipt_table_lines: stable logical receipt-line identity
- purchase_import_lines: approval/unpacking work state
- inventory_events: actual inventory effects

No user-facing delete/reimport behaviour is changed by this module.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text


ACTIVE = "active"
LEGACY_DELETED = "legacy_deleted"
ALLOWED_WORKFLOW_STATES = {
    ACTIVE,
    "archived",
    "returned_to_kassa",
    "removed_reimport_allowed",
    LEGACY_DELETED,
}


def _columns(conn, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    }


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = :name LIMIT 1"
            ),
            {"name": table_name},
        ).scalar()
    )


def ensure_receipt_lifecycle_foundation_schema(conn) -> dict[str, Any]:
    """Idempotently add only non-derivable receipt lifecycle facts.

    Deliberately NOT added:
    - receipt identity tables;
    - receipt-line processing tables;
    - duplicated approved/unpacked flags;
    - archive copies of receipts;
    - a second inventory ledger.
    """
    required = ("raw_receipts", "receipt_tables", "receipt_table_lines")
    missing = [name for name in required if not _table_exists(conn, name)]
    if missing:
        raise RuntimeError(
            "Receipt basisdatamodel ontbreekt: " + ", ".join(sorted(missing))
        )

    raw_columns = _columns(conn, "raw_receipts")
    receipt_columns = _columns(conn, "receipt_tables")
    line_columns = _columns(conn, "receipt_table_lines")

    added: list[str] = []

    if "logical_receipt_key" not in receipt_columns:
        conn.execute(text("ALTER TABLE receipt_tables ADD COLUMN logical_receipt_key TEXT"))
        added.append("receipt_tables.logical_receipt_key")
    if "workflow_state" not in receipt_columns:
        conn.execute(
            text(
                "ALTER TABLE receipt_tables "
                "ADD COLUMN workflow_state TEXT NOT NULL DEFAULT 'active'"
            )
        )
        added.append("receipt_tables.workflow_state")
    if "logical_line_key" not in line_columns:
        conn.execute(text("ALTER TABLE receipt_table_lines ADD COLUMN logical_line_key TEXT"))
        added.append("receipt_table_lines.logical_line_key")

    # Existing rows receive opaque stable identities. Future reimport/reconciliation
    # may deliberately reuse these keys on a new import attempt.
    missing_receipts = [
        str(row[0])
        for row in conn.execute(
            text(
                "SELECT id FROM receipt_tables "
                "WHERE COALESCE(trim(logical_receipt_key), '') = ''"
            )
        ).fetchall()
    ]
    for receipt_id in missing_receipts:
        conn.execute(
            text(
                "UPDATE receipt_tables SET logical_receipt_key = :key "
                "WHERE id = :id"
            ),
            {"id": receipt_id, "key": uuid.uuid4().hex},
        )

    missing_lines = [
        str(row[0])
        for row in conn.execute(
            text(
                "SELECT id FROM receipt_table_lines "
                "WHERE COALESCE(trim(logical_line_key), '') = ''"
            )
        ).fetchall()
    ]
    for line_id in missing_lines:
        conn.execute(
            text(
                "UPDATE receipt_table_lines SET logical_line_key = :key "
                "WHERE id = :id"
            ),
            {"id": line_id, "key": uuid.uuid4().hex},
        )

    # Existing deleted_at rows predate the new semantic distinction between
    # archive and removal. Do not invent intent retrospectively.
    if "deleted_at" in receipt_columns:
        conn.execute(
            text(
                "UPDATE receipt_tables "
                "SET workflow_state = :legacy_deleted "
                "WHERE deleted_at IS NOT NULL "
                "AND COALESCE(workflow_state, 'active') = 'active'"
            ),
            {"legacy_deleted": LEGACY_DELETED},
        )
    conn.execute(
        text(
            "UPDATE receipt_tables SET workflow_state = 'active' "
            "WHERE COALESCE(trim(workflow_state), '') = ''"
        )
    )

    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_receipt_tables_logical_receipt_key "
            "ON receipt_tables (household_id, logical_receipt_key)"
        )
    )
    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_table_lines_logical_line_key "
            "ON receipt_table_lines (logical_line_key) "
            "WHERE logical_line_key IS NOT NULL AND trim(logical_line_key) <> ''"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_receipt_tables_workflow_state "
            "ON receipt_tables (household_id, workflow_state)"
        )
    )

    # Preserve the original source hash. Reimport of a soft-deleted exact source
    # must eventually be enabled by active-row uniqueness, not by mutating hashes.
    # Release A changes only the index contract; current delete behaviour is left
    # untouched until Release B.
    if "deleted_at" in raw_columns:
        conn.execute(text("DROP INDEX IF EXISTS uq_raw_receipts_household_hash"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_receipts_household_hash "
                "ON raw_receipts (household_id, sha256_hash) "
                "WHERE deleted_at IS NULL"
            )
        )

    return {
        "added_columns": added,
        "backfilled_receipts": len(missing_receipts),
        "backfilled_lines": len(missing_lines),
        "workflow_states": sorted(ALLOWED_WORKFLOW_STATES),
    }


def install_receipt_lifecycle_foundation(app, engine) -> None:
    """Register the idempotent schema foundation on FastAPI startup."""
    marker = "_rezzerv_receipt_lifecycle_foundation_installed"
    if getattr(app.state, marker, False):
        return

    async def _ensure_on_startup() -> None:
        with engine.begin() as conn:
            ensure_receipt_lifecycle_foundation_schema(conn)

    app.add_event_handler("startup", _ensure_on_startup)
    setattr(app.state, marker, True)
