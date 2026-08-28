"""Receipt lifecycle business logic for safe delete/reimport semantics.

The database schema and receipt lifecycle invariants are owned by Alembic. This
module contains only runtime business/data reconciliation and lifecycle actions.
Persisted facts keep one source of truth:

- receipt_tables: current receipt workflow + stable logical receipt identity
- receipt_table_lines: stable logical receipt-line identity
- purchase_import_lines: approval/unpacking work state
- inventory_events: actual inventory effects

Explicit user approval is a lifecycle fact. Technical parser/status backfills may
refresh diagnostics, but may not silently invalidate an existing approval. An
approved active receipt therefore remains approved and visible to Uitpakken until
a user explicitly returns it to Kassa, archives it, or removes it.
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
APPROVED = "approved"
APPROVED_OVERRIDE = "approved_override"
NON_ACTIVE_WORKFLOW_STATES = {
    ARCHIVED,
    REMOVED_REIMPORT_ALLOWED,
    LEGACY_DELETED,
}
APPROVAL_GUARD_TRIGGER = "trg_receipt_tables_preserve_explicit_approval"


def ensure_explicit_approval_guard_trigger(conn) -> None:
    """Compatibility shim; Alembic owns the receipt approval guard trigger."""
    del conn


def ensure_receipt_lifecycle_foundation_schema(conn) -> None:
    """Compatibility shim; Alembic owns the receipt lifecycle schema."""
    del conn


def reconcile_explicit_receipt_approvals(
    conn,
    *,
    receipt_table_id: str | None = None,
) -> dict[str, Any]:
    """Restore technical parse status to the persisted user approval decision.

    ``approved_at`` is the lifecycle fact that moves a receipt from Kassa into the
    approved/Uitpakken flow. Parser diagnostics are allowed to change later, but a
    background recalculation must never make that explicit approval disappear.

    This reconciliation repairs only active, non-deleted receipts that still have
    ``approved_at``. It never creates approval, never clears approval, never
    reactivates archived/removed receipts and never touches inventory facts.
    The canonical Alembic contract guarantees the columns used here exist.
    """
    params: dict[str, Any] = {
        "approved": APPROVED,
        "approved_override": APPROVED_OVERRIDE,
        "archived": ARCHIVED,
        "removed": REMOVED_REIMPORT_ALLOWED,
        "legacy_deleted": LEGACY_DELETED,
    }
    id_filter = ""
    normalized_receipt_id = str(receipt_table_id or "").strip()
    if normalized_receipt_id:
        id_filter = " AND rt.id = :receipt_table_id"
        params["receipt_table_id"] = normalized_receipt_id

    rows = conn.execute(
        text(
            f"""
            SELECT rt.id
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE rt.approved_at IS NOT NULL
              AND rt.deleted_at IS NULL
              AND rr.deleted_at IS NULL
              AND lower(trim(COALESCE(rt.parse_status, ''))) NOT IN (
                    :approved, :approved_override
              )
              AND lower(trim(COALESCE(rt.workflow_state, 'active'))) NOT IN (
                    :archived, :removed, :legacy_deleted
              )
              {id_filter}
            ORDER BY rt.id
            """
        ),
        params,
    ).fetchall()
    receipt_ids = [str(row[0]) for row in rows]

    for candidate_id in receipt_ids:
        conn.execute(
            text(
                """
                UPDATE receipt_tables
                SET parse_status = CASE
                        WHEN COALESCE(totals_overridden, FALSE)
                        THEN 'approved_override'
                        ELSE 'approved'
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :receipt_table_id
                """
            ),
            {"receipt_table_id": candidate_id},
        )

    return {
        "reconciled_count": len(receipt_ids),
        "receipt_table_ids": receipt_ids,
    }


def reconcile_receipt_lifecycle_foundation_data(conn) -> dict[str, Any]:
    """Idempotently reconcile persisted lifecycle data on the canonical schema.

    This intentionally performs no schema inspection or mutation. Historical rows
    may still need stable logical keys or a non-ambiguous workflow state, and an
    explicit user approval remains authoritative over later parser diagnostics.
    """
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

    # Existing deleted_at rows predate the semantic distinction between archive
    # and removal. Do not invent intent retrospectively.
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

    approval_reconciliation = reconcile_explicit_receipt_approvals(conn)
    return {
        "backfilled_receipts": len(missing_receipts),
        "backfilled_lines": len(missing_lines),
        "workflow_states": sorted(ALLOWED_WORKFLOW_STATES),
        "reconciled_explicit_approvals": approval_reconciliation["reconciled_count"],
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
    if (
        not expected_household_id
        or receipt_household_id != expected_household_id
        or batch_household_id != expected_household_id
    ):
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
    """Reconcile receipt lifecycle data once after Alembic has validated schema."""
    marker = "_rezzerv_receipt_lifecycle_foundation_installed"
    if getattr(app.state, marker, False):
        return

    with engine.begin() as conn:
        reconcile_receipt_lifecycle_foundation_data(conn)

    setattr(app.state, marker, True)
