from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine, get_runtime_datastore_info

router = APIRouter(prefix="/api/testing", tags=["testing"])

STATUS_LABELS_NL = {
    "approved": "Gecontroleerd",
    "parsed": "Gecontroleerd",
    "review_needed": "Controle nodig",
    "manual": "Handmatig",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in dict(row).items()}


def _count_by_status(rows: list[dict[str, Any]], use_labels: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        raw_status = str(row.get("parse_status") or "onbekend")
        key = STATUS_LABELS_NL.get(raw_status, raw_status) if use_labels else raw_status
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_receipt_db_snapshot(include_deleted: bool = False, limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    with engine.connect() as conn:
        datastore_info = get_runtime_datastore_info()
        active_filter = "" if include_deleted else "where rt.deleted_at is null"

        receipt_rows = [
            _row_to_dict(row)
            for row in conn.execute(
                text(
                    f"""
                    select
                        rt.id,
                        rt.raw_receipt_id,
                        rt.household_id,
                        rt.store_name,
                        rt.store_branch,
                        rt.purchase_at,
                        rt.total_amount,
                        rt.currency,
                        rt.parse_status,
                        rt.confidence_score,
                        rt.line_count,
                        rt.created_at,
                        rt.updated_at,
                        rt.deleted_at,
                        rt.discount_total,
                        rr.original_filename,
                        rr.raw_status,
                        rr.imported_at,
                        rr.sha256_hash
                    from receipt_tables rt
                    left join raw_receipts rr on rr.id = rt.raw_receipt_id
                    {active_filter}
                    order by rt.created_at desc
                    limit :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings()
        ]

        line_stats = {
            str(row["receipt_table_id"]): _row_to_dict(row)
            for row in conn.execute(
                text(
                    """
                    select
                        receipt_table_id,
                        count(*) as line_count_actual,
                        round(coalesce(sum(coalesce(line_total, 0)), 0), 2) as line_sum,
                        round(coalesce(sum(coalesce(discount_amount, 0)), 0), 2) as discount_sum,
                        round(avg(confidence_score), 4) as average_line_confidence
                    from receipt_table_lines
                    group by receipt_table_id
                    """
                )
            ).mappings()
        }

        recent_runs = [
            _row_to_dict(row)
            for row in conn.execute(
                text(
                    """
                    select id, source_id, started_at, finished_at, files_found, files_imported, files_skipped, files_failed
                    from receipt_processing_runs
                    order by started_at desc
                    limit 10
                    """
                )
            ).mappings()
        ]

        total_receipt_tables = int(conn.execute(text("select count(*) from receipt_tables")).scalar_one())
        deleted_receipt_tables = int(
            conn.execute(text("select count(*) from receipt_tables where deleted_at is not null")).scalar_one()
        )

    enriched_receipts: list[dict[str, Any]] = []
    for receipt in receipt_rows:
        receipt_id = str(receipt["id"])
        stats = line_stats.get(receipt_id, {})
        line_sum = stats.get("line_sum")
        total_amount = receipt.get("total_amount")
        financial_difference = None
        try:
            if total_amount is not None and line_sum is not None:
                financial_difference = round(float(total_amount) - float(line_sum), 2)
        except (TypeError, ValueError):
            financial_difference = None
        raw_status = str(receipt.get("parse_status") or "")
        enriched_receipts.append(
            {
                **receipt,
                "status_label_nl": STATUS_LABELS_NL.get(raw_status, raw_status),
                "line_stats": stats,
                "financial_difference": financial_difference,
            }
        )

    active_receipts = [row for row in enriched_receipts if row.get("deleted_at") in (None, "")]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Rezzerv kassabon database snapshot voor scrumteam-analyse na een PO-run.",
        "runtime_datastore": datastore_info,
        "summary": {
            "total_receipt_tables": total_receipt_tables,
            "deleted_receipt_tables": deleted_receipt_tables,
            "returned_receipts": len(enriched_receipts),
            "active_returned_receipts": len(active_receipts),
            "status_counts_nl": _count_by_status(active_receipts, True),
            "status_counts_raw": _count_by_status(active_receipts, False),
        },
        "recent_processing_runs": recent_runs,
        "receipts": enriched_receipts,
    }


@router.get("/receipt-db-snapshot")
def get_receipt_db_snapshot(
    include_deleted: bool = Query(False, description="Neem ook soft-deleted kassabonnen mee."),
    limit: int = Query(500, ge=1, le=2000, description="Maximaal aantal kassabonnen in de snapshot."),
):
    return build_receipt_db_snapshot(include_deleted=include_deleted, limit=limit)


@router.get("/receipt-db-snapshot/download")
def download_receipt_db_snapshot(
    include_deleted: bool = Query(False, description="Neem ook soft-deleted kassabonnen mee."),
    limit: int = Query(500, ge=1, le=2000, description="Maximaal aantal kassabonnen in de snapshot."),
):
    snapshot = build_receipt_db_snapshot(include_deleted=include_deleted, limit=limit)
    filename = f"rezzerv_receipt_db_snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(
        content=snapshot,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
