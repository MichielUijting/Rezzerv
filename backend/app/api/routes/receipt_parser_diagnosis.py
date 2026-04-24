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


def _sum_values(rows: list[dict[str, Any]], key: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _difference(total_amount: Any, line_sum: float) -> float | None:
    try:
        if total_amount is not None:
            return round(float(total_amount) - float(line_sum), 2)
    except (TypeError, ValueError):
        return None
    return None


def build_receipt_parser_diagnosis(include_deleted: bool = False, limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    with engine.connect() as conn:
        datastore_info = get_runtime_datastore_info()
        active_filter = "" if include_deleted else "where rt.deleted_at is null"
        receipts = [
            _row_to_dict(row)
            for row in conn.execute(
                text(
                    f"""
                    select
                        rt.id,
                        rt.raw_receipt_id,
                        rt.store_name,
                        rt.store_branch,
                        rt.purchase_at,
                        rt.total_amount,
                        rt.parse_status,
                        rt.confidence_score,
                        rt.line_count,
                        rt.discount_total,
                        rt.deleted_at,
                        rr.original_filename,
                        rr.raw_status
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
        lines = [
            _row_to_dict(row)
            for row in conn.execute(
                text(
                    """
                    select
                        id,
                        receipt_table_id,
                        article_name,
                        quantity,
                        unit,
                        unit_price,
                        line_total,
                        discount_amount,
                        confidence_score,
                        is_deleted
                    from receipt_table_lines
                    order by receipt_table_id, id
                    """
                )
            ).mappings()
        ]

    lines_by_receipt: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        lines_by_receipt.setdefault(str(line.get("receipt_table_id")), []).append(line)

    diagnoses: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for receipt in receipts:
        receipt_id = str(receipt["id"])
        raw_status = str(receipt.get("parse_status") or "onbekend")
        status_label = STATUS_LABELS_NL.get(raw_status, raw_status)
        status_counts[status_label] = status_counts.get(status_label, 0) + 1
        receipt_lines = lines_by_receipt.get(receipt_id, [])
        accepted_lines = []
        rejected_lines = []
        for index, line in enumerate(receipt_lines, start=1):
            item = {
                "id": line.get("id"),
                "line_number": index,
                "text": line.get("article_name"),
                "article_name": line.get("article_name"),
                "quantity": line.get("quantity"),
                "unit": line.get("unit"),
                "unit_price": line.get("unit_price"),
                "line_total": line.get("line_total"),
                "discount_amount": line.get("discount_amount"),
                "confidence_score": line.get("confidence_score"),
            }
            if line.get("is_deleted") in (1, True, "1", "true", "True"):
                rejected_lines.append({**item, "reason": "Regel is in de database gemarkeerd als verwijderd."})
            else:
                accepted_lines.append(item)
        line_sum = _sum_values(accepted_lines, "line_total")
        discount_sum = _sum_values(accepted_lines, "discount_amount")
        diagnoses.append(
            {
                "filename": receipt.get("original_filename"),
                "receipt_table_id": receipt_id,
                "raw_receipt_id": receipt.get("raw_receipt_id"),
                "store_name": receipt.get("store_name"),
                "store_branch": receipt.get("store_branch"),
                "purchase_at": receipt.get("purchase_at"),
                "parse_status": raw_status,
                "status_label_nl": status_label,
                "confidence_score": receipt.get("confidence_score"),
                "ocr_lines": [],
                "normalized_lines": [line.get("article_name") for line in accepted_lines if line.get("article_name")],
                "accepted_lines": accepted_lines,
                "rejected_lines": rejected_lines,
                "financials": {
                    "total_amount": receipt.get("total_amount"),
                    "line_sum": line_sum,
                    "discount_sum": discount_sum,
                    "difference": _difference(receipt.get("total_amount"), line_sum),
                    "line_count_reported": receipt.get("line_count"),
                    "line_count_actual": len(accepted_lines),
                },
                "status_decision": {
                    "parse_status": raw_status,
                    "status_label_nl": status_label,
                    "raw_status": receipt.get("raw_status"),
                    "source": "receipt_tables.parse_status",
                },
                "diagnosis_notes": [
                    "Read-only diagnose: parser, OCR, statusclassificatie en UI worden niet gewijzigd.",
                    "Ruwe OCR-regels en parser-afwijzingsredenen zijn alleen beschikbaar als ze al in de database worden opgeslagen.",
                ],
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Rezzerv receipt parser diagnose v2 voor generieke parserverbetering zonder bonspecifieke fixes.",
        "runtime_datastore": datastore_info,
        "summary": {"returned_receipts": len(diagnoses), "status_counts_nl": status_counts},
        "diagnosis_scope": {
            "read_only": True,
            "parser_changed": False,
            "ocr_changed": False,
            "status_classification_changed": False,
            "ui_changed": False,
            "bonspecific_fixes": False,
        },
        "receipts": diagnoses,
    }


@router.get("/receipt-parser-diagnosis")
def get_receipt_parser_diagnosis(
    include_deleted: bool = Query(False, description="Neem ook soft-deleted kassabonnen mee."),
    limit: int = Query(500, ge=1, le=2000, description="Maximaal aantal kassabonnen in de diagnose."),
):
    return build_receipt_parser_diagnosis(include_deleted=include_deleted, limit=limit)


@router.get("/receipt-parser-diagnosis/download")
def download_receipt_parser_diagnosis(
    include_deleted: bool = Query(False, description="Neem ook soft-deleted kassabonnen mee."),
    limit: int = Query(500, ge=1, le=2000, description="Maximaal aantal kassabonnen in de diagnose."),
):
    diagnosis = build_receipt_parser_diagnosis(include_deleted=include_deleted, limit=limit)
    filename = f"rezzerv_receipt_parser_diagnosis_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(content=diagnosis, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
