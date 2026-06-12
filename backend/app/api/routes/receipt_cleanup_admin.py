from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import bindparam, text

from app.db import engine
from app.main import require_household_admin_context
from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline

router = APIRouter(prefix="/api/dev/receipts", tags=["admin", "receipts"])


class PurgeDeletedReceiptsRequest(BaseModel):
    household_id: Optional[str] = None


@router.get("/po-status-labels")
def get_po_status_labels(household_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Statusmap voor Kassa volgens de PO-norm.

    Dit endpoint bepaalt geen status zelf. Het exposeert uitsluitend de uitkomst
    van receipt_status_baseline_service_v4.py zodat UI/API dezelfde bron gebruiken.
    """
    context = require_household_admin_context(authorization, household_id)
    effective_household_id = str(context.get("active_household_id") or household_id or "").strip() or None
    with engine.connect() as conn:
        validation = validate_receipt_status_baseline(conn, household_id=effective_household_id)
    labels = {}
    for item in validation.get("details", []) or []:
        receipt_table_id = str(item.get("receipt_table_id") or "").strip()
        if not receipt_table_id:
            continue
        labels[receipt_table_id] = {
            "po_norm_status": item.get("po_norm_status") or "review_needed",
            "po_norm_status_label": item.get("po_norm_status_label") or "Controle nodig",
            "failed_criteria": item.get("failed_criteria") or [],
            "result": item.get("result"),
            "reason": item.get("reason"),
        }
    po_counts = validation.get("summary", {}).get("po_norm_status_counts", {}) or {}
    return {
        "policy_source": "receipt_status_baseline_service_v4.py",
        "status_source": "po_norm_status_label",
        "household_id": effective_household_id,
        "labels": labels,
        "po_norm_status_counts": po_counts,
        "backend_status_counts": po_counts,
        "difference": 0,
    }


@router.post("/purge-deleted")
def purge_deleted_receipts(payload: PurgeDeletedReceiptsRequest, authorization: Optional[str] = Header(None)):
    """Definitief opschonen van soft-deleted kassabonnen voor testomgevingen.

    Scope: alleen records die al deleted_at hebben. Dit wijzigt geen parser,
    baseline, actieve kassabonnen of inleesproces.
    """
    context = require_household_admin_context(authorization, payload.household_id)
    effective_household_id = str(context.get("active_household_id") or payload.household_id or "").strip()
    if not effective_household_id:
        raise HTTPException(status_code=400, detail="household_id ontbreekt")

    with engine.begin() as conn:
        receipt_rows = conn.execute(
            text(
                """
                SELECT id, raw_receipt_id
                FROM receipt_tables
                WHERE household_id = :household_id
                  AND deleted_at IS NOT NULL
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()

        receipt_ids = [str(row["id"]) for row in receipt_rows if row.get("id")]
        raw_ids = [str(row["raw_receipt_id"]) for row in receipt_rows if row.get("raw_receipt_id")]
        source_references = [f"receipt:{receipt_id}" for receipt_id in receipt_ids]

        batch_ids: list[str] = []
        if source_references:
            batch_ids = [
                str(row["id"])
                for row in conn.execute(
                    text(
                        """
                        SELECT id
                        FROM purchase_import_batches
                        WHERE household_id = :household_id
                          AND source_reference IN :source_references
                        """
                    ).bindparams(bindparam("source_references", expanding=True)),
                    {"household_id": effective_household_id, "source_references": source_references},
                ).mappings().all()
                if row.get("id")
            ]

        deleted_counts = {
            "receipt_table_lines": 0,
            "receipt_inbound_events": 0,
            "receipt_email_messages": 0,
            "purchase_import_lines": 0,
            "purchase_import_batches": 0,
            "receipt_tables": 0,
            "raw_receipts": 0,
        }

        if batch_ids:
            result = conn.execute(
                text("DELETE FROM purchase_import_lines WHERE batch_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": batch_ids},
            )
            deleted_counts["purchase_import_lines"] = int(result.rowcount or 0)
            result = conn.execute(
                text("DELETE FROM purchase_import_batches WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": batch_ids},
            )
            deleted_counts["purchase_import_batches"] = int(result.rowcount or 0)

        if receipt_ids:
            result = conn.execute(
                text("DELETE FROM receipt_table_lines WHERE receipt_table_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": receipt_ids},
            )
            deleted_counts["receipt_table_lines"] = int(result.rowcount or 0)
            result = conn.execute(
                text("DELETE FROM receipt_inbound_events WHERE receipt_table_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": receipt_ids},
            )
            deleted_counts["receipt_inbound_events"] = int(result.rowcount or 0)
            result = conn.execute(
                text("DELETE FROM receipt_tables WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": receipt_ids},
            )
            deleted_counts["receipt_tables"] = int(result.rowcount or 0)

        if raw_ids:
            result = conn.execute(
                text("DELETE FROM receipt_email_messages WHERE raw_receipt_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": raw_ids},
            )
            deleted_counts["receipt_email_messages"] = int(result.rowcount or 0)
            result = conn.execute(
                text("DELETE FROM receipt_inbound_events WHERE raw_receipt_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": raw_ids},
            )
            deleted_counts["receipt_inbound_events"] += int(result.rowcount or 0)
            result = conn.execute(
                text("DELETE FROM raw_receipts WHERE id IN :ids AND deleted_at IS NOT NULL").bindparams(bindparam("ids", expanding=True)),
                {"ids": raw_ids},
            )
            deleted_counts["raw_receipts"] = int(result.rowcount or 0)

    return {
        "household_id": effective_household_id,
        "purged_receipt_count": len(receipt_ids),
        "purged_raw_receipt_count": deleted_counts["raw_receipts"],
        "deleted_counts": deleted_counts,
        "scope": "soft_deleted_receipts_only",
    }
