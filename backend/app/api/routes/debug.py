from __future__ import annotations

import traceback
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from app.db import engine
from app.main import get_receipt_detail, require_entity_household_access
from app.services.receipt_service import parse_receipt_content, serialize_receipt_row

router = APIRouter()


def _debug_json_safe(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _debug_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_debug_json_safe(v) for v in value]
    if hasattr(value, "_mapping"):
        try:
            return _debug_json_safe(dict(value._mapping))
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        try:
            return _debug_json_safe(vars(value))
        except Exception:
            return str(value)
    return str(value)


@router.get("/api/receipts/{receipt_table_id}/debug-export")
def export_receipt_debug(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_tables", receipt_table_id, authorization, admin_only=False)
        record = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.reference,
                    rt.notes,
                    rt.created_at,
                    rt.updated_at,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rr.sha256_hash,
                    rr.imported_at,
                    rr.raw_status,
                    rem.sender_email,
                    rem.sender_name,
                    rem.subject AS email_subject,
                    rem.received_at AS email_received_at,
                    rem.body_text,
                    rem.body_html,
                    rem.selected_part_type,
                    rem.selected_filename AS email_selected_filename,
                    rem.selected_mime_type AS email_selected_mime_type
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.id = :receipt_table_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().first()
        if not record:
            raise HTTPException(status_code=404, detail="Bon niet gevonden")
        lines = conn.execute(
            text(
                """
                SELECT
                    id,
                    line_index,
                    raw_label,
                    corrected_raw_label,
                    normalized_label,
                    quantity,
                    corrected_quantity,
                    unit,
                    corrected_unit,
                    unit_price,
                    corrected_unit_price,
                    line_total,
                    corrected_line_total,
                    discount_amount,
                    barcode,
                    article_match_status,
                    matched_article_id,
                    matched_global_product_id,
                    confidence_score,
                    COALESCE(is_deleted, 0) AS is_deleted,
                    COALESCE(is_validated, 0) AS is_validated,
                    created_at,
                    updated_at
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, created_at ASC
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().all()

    detail_payload = None
    detail_error = None
    detail_traceback = None
    try:
        detail_payload = get_receipt_detail(receipt_table_id, authorization)
    except Exception as exc:
        detail_error = str(exc)
        detail_traceback = traceback.format_exc()
    storage_path = Path(str(record.get("storage_path") or "")).resolve() if record.get("storage_path") else None
    source_exists = bool(storage_path and storage_path.exists() and storage_path.is_file())
    reparsed = None
    source_excerpt = None
    source_error = None

    try:
        if source_exists and storage_path is not None:
            raw_bytes = storage_path.read_bytes()
            parsed = parse_receipt_content(raw_bytes, str(record.get("original_filename") or storage_path.name), str(record.get("mime_type") or "application/octet-stream"))
            reparsed = {
                "is_receipt": parsed.is_receipt,
                "parse_status": parsed.parse_status,
                "confidence_score": parsed.confidence_score,
                "store_name": parsed.store_name,
                "store_branch": parsed.store_branch,
                "purchase_at": parsed.purchase_at,
                "total_amount": float(parsed.total_amount) if parsed.total_amount is not None else None,
                "discount_total": float(parsed.discount_total) if parsed.discount_total is not None else None,
                "currency": parsed.currency,
                "lines": _debug_json_safe(parsed.lines or []),
            }
            mime_type = str(record.get("mime_type") or "").lower()
            filename = str(record.get("original_filename") or "").lower()
            if mime_type.startswith("text/") or filename.endswith((".txt", ".csv", ".json", ".xml", ".html", ".htm", ".eml")):
                source_excerpt = raw_bytes[:12000].decode("utf-8", errors="replace")
    except Exception as exc:
        source_error = str(exc)

    payload = {
        "receipt": detail_payload,
        "detail_error": detail_error,
        "detail_traceback": detail_traceback,
        "storage": {
            "raw_receipt_id": record.get("raw_receipt_id"),
            "original_filename": record.get("original_filename"),
            "mime_type": record.get("mime_type"),
            "storage_path": str(storage_path) if storage_path else None,
            "storage_exists": source_exists,
            "sha256_hash": record.get("sha256_hash"),
            "imported_at": record.get("imported_at"),
            "raw_status": record.get("raw_status"),
        },
        "email_message": {
            "sender_email": record.get("sender_email"),
            "sender_name": record.get("sender_name"),
            "subject": record.get("email_subject"),
            "received_at": record.get("email_received_at"),
            "selected_part_type": record.get("selected_part_type"),
            "selected_filename": record.get("email_selected_filename"),
            "selected_mime_type": record.get("email_selected_mime_type"),
            "body_text_excerpt": (str(record.get("body_text") or "")[:12000] or None),
            "body_html_excerpt": (str(record.get("body_html") or "")[:12000] or None),
        },
        "stored_lines_raw": [serialize_receipt_row(dict(line)) for line in lines],
        "reparsed_from_source": reparsed,
        "source_excerpt": source_excerpt,
        "source_error": source_error,
        "exported_at": datetime.utcnow().isoformat() + "Z",
    }
    safe_payload = _debug_json_safe(payload)
    return JSONResponse(content=jsonable_encoder(safe_payload))
