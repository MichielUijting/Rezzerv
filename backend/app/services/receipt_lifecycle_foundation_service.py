"""Minimal receipt lifecycle foundation for safe delete/reimport semantics.

Release A deliberately extends existing receipt entities instead of introducing
parallel identity or processing tables. Persisted facts keep one source of truth:

- receipt_tables: current receipt workflow + stable logical receipt identity
- receipt_table_lines: stable logical receipt-line identity
- purchase_import_lines: approval/unpacking work state
- inventory_events: actual inventory effects

Release B adds explicit disposition actions for receipts that are already in the
Uitpakken flow. These actions deliberately do not reverse inventory events.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text


ACTIVE = "active"
LEGACY_DELETED = "legacy_deleted"
RETURNED_TO_KASSA = "returned_to_kassa"
ARCHIVED = "archived"
REMOVED_REIMPORT_ALLOWED = "removed_reimport_allowed"
ALLOWED_WORKFLOW_STATES = {
    ACTIVE,
    ARCHIVED,
    RETURNED_TO_KASSA,
    REMOVED_REIMPORT_ALLOWED,
    LEGACY_DELETED,
}
UNPACK_LIFECYCLE_ACTIONS = {"return_to_kassa", "archive"}


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
    # deliberately reuses these keys on a newer import attempt of the same logical
    # receipt/line; therefore the key columns themselves are indexed, not unique.
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
    # Remove an accidental early Release-A development index if it ever existed.
    conn.execute(text("DROP INDEX IF EXISTS uq_receipt_table_lines_logical_line_key"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_receipt_table_lines_logical_line_key "
            "ON receipt_table_lines (logical_line_key)"
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


def resolve_receipt_for_unpack_batch(conn, batch_id: str) -> dict[str, Any] | None:
    """Resolve the canonical receipt behind a receipt-backed Uitpakken batch."""
    batch = conn.execute(
        text(
            """
            SELECT id, household_id, source_type, source_reference, import_status
            FROM purchase_import_batches
            WHERE id = :batch_id
            LIMIT 1
            """
        ),
        {"batch_id": str(batch_id or "").strip()},
    ).mappings().first()
    if not batch or str(batch.get("source_type") or "").strip() != "receipt":
        return None

    source_reference = str(batch.get("source_reference") or "").strip()
    if not source_reference.startswith("receipt:"):
        return None
    receipt_table_id = source_reference.split(":", 1)[1].strip()
    if not receipt_table_id:
        return None

    receipt = conn.execute(
        text(
            """
            SELECT id, household_id, raw_receipt_id, approved_at, deleted_at,
                   COALESCE(workflow_state, 'active') AS workflow_state
            FROM receipt_tables
            WHERE id = :receipt_table_id
            LIMIT 1
            """
        ),
        {"receipt_table_id": receipt_table_id},
    ).mappings().first()
    if not receipt:
        return None

    result = dict(receipt)
    result["batch_id"] = str(batch["id"])
    result["batch_household_id"] = str(batch["household_id"])
    result["import_status"] = str(batch.get("import_status") or "")
    return result


def apply_unpack_receipt_lifecycle_action(
    conn,
    *,
    batch_id: str,
    household_id: str,
    action: str,
) -> dict[str, Any]:
    """Apply an explicit Uitpakken receipt disposition without inventory reversal."""
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in UNPACK_LIFECYCLE_ACTIONS:
        raise ValueError(f"Onbekende lifecycle-actie: {normalized_action or '-'}")

    receipt = resolve_receipt_for_unpack_batch(conn, batch_id)
    if not receipt:
        raise LookupError("Geen kassabon gevonden voor deze Uitpakken-batch")

    expected_household_id = str(household_id or "").strip()
    receipt_household_id = str(receipt.get("household_id") or "").strip()
    batch_household_id = str(receipt.get("batch_household_id") or "").strip()
    if not expected_household_id or receipt_household_id != expected_household_id or batch_household_id != expected_household_id:
        raise PermissionError("Kassabon hoort niet bij het actieve huishouden")

    receipt_table_id = str(receipt["id"])
    if normalized_action == "return_to_kassa":
        conn.execute(
            text(
                """
                UPDATE receipt_tables
                SET approved_at = NULL,
                    workflow_state = :workflow_state,
                    deleted_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :receipt_table_id
                  AND household_id = :household_id
                """
            ),
            {
                "workflow_state": RETURNED_TO_KASSA,
                "receipt_table_id": receipt_table_id,
                "household_id": expected_household_id,
            },
        )
        return {
            "status": "ok",
            "action": normalized_action,
            "batch_id": str(batch_id),
            "receipt_table_id": receipt_table_id,
            "workflow_state": RETURNED_TO_KASSA,
            "inventory_events_reversed": False,
        }

    # Archive retains all receipt/import/inventory facts but hides the receipt from
    # the active Kassa/Uitpakken queries through receipt_tables.deleted_at. Unlike
    # full removal, raw_receipts stays active so the original source hash remains
    # reserved and the exact source cannot be reimported as a new active receipt.
    conn.execute(
        text(
            """
            UPDATE receipt_tables
            SET workflow_state = :workflow_state,
                deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :receipt_table_id
              AND household_id = :household_id
            """
        ),
        {
            "workflow_state": ARCHIVED,
            "receipt_table_id": receipt_table_id,
            "household_id": expected_household_id,
        },
    )
    conn.execute(
        text(
            """
            UPDATE purchase_import_batches
            SET import_status = 'archived'
            WHERE id = :batch_id
              AND household_id = :household_id
            """
        ),
        {"batch_id": str(batch_id), "household_id": expected_household_id},
    )
    return {
        "status": "ok",
        "action": normalized_action,
        "batch_id": str(batch_id),
        "receipt_table_id": receipt_table_id,
        "workflow_state": ARCHIVED,
        "inventory_events_reversed": False,
    }


def install_receipt_lifecycle_foundation(app, engine) -> None:
    """Apply the Release-A foundation once when the loaded runtime is ready.

    app.__init__ already waits until app.main has created the FastAPI app, engine,
    receipt schema and delete route. Registering another FastAPI startup handler at
    that late point is unsafe because the startup phase may already have passed.
    Therefore the same idempotent schema function is executed directly here.
    """
    marker = "_rezzerv_receipt_lifecycle_foundation_installed"
    if getattr(app.state, marker, False):
        return

    with engine.begin() as conn:
        ensure_receipt_lifecycle_foundation_schema(conn)

    setattr(app.state, marker, True)
