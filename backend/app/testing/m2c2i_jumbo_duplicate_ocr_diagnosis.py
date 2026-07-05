"""M2C2i Jumbo duplicate + raw OCR diagnosis.

Run:
  docker compose exec backend sh -lc 'cd /app && PYTHONPATH=/app python app/testing/m2c2i_jumbo_duplicate_ocr_diagnosis.py'

This runner is read-only: it queries current raw_receipts/receipt_tables,
runs raw OCR and preprocessed OCR for the selected Jumbo images, reparses the
same source file, and writes a JSON report under reports/.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing
from app.receipt_ingestion.service_parts.image_ocr_flow import _ocr_image_text_with_paddle, _ocr_image_text_with_tesseract
from app.receipt_ingestion.service_parts.source_detection import detect_mime_type
from app.services.receipt_service import parse_receipt_content

DEFAULT_FILENAMES = [
    "Jumbo foto 11.jpeg",
    "Jumbo foto 12.jpeg",
    "Jumbo foto 13.jpeg",
    "Jumbo foto 14.jpeg",
    "Jumbo foto 15.jpeg",
]
AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,5}[\.,]\d{2})(?!\d)")


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def clean_label(value: Any) -> str:
    text_value = AMOUNT_RE.sub(" ", str(value or "").lower())
    text_value = re.sub(r"[^a-z0-9à-öø-ÿ]+", " ", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def signature(label: Any, amount: Any) -> str:
    return f"{clean_label(label)}|{dec(amount)}"


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def load_rows(filenames: list[str]) -> list[dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    for index, filename in enumerate(filenames):
        key = f"filename_{index}"
        clauses.append(f"rr.original_filename = :{key}")
        params[key] = filename
    where_sql = " OR ".join(clauses) or "lower(COALESCE(rr.original_filename, '')) LIKE 'jumbo foto %.jpeg'"
    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT rr.id AS raw_receipt_id, rr.household_id, rr.original_filename,
                   rr.mime_type, rr.storage_path, rr.sha256_hash, rr.raw_status,
                   rr.imported_at, rt.id AS receipt_table_id, rt.store_name,
                   rt.store_branch, rt.purchase_at, rt.total_amount, rt.discount_total,
                   rt.parse_status, rt.line_count, rt.deleted_at AS receipt_deleted_at
            FROM raw_receipts rr
            LEFT JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
            WHERE rr.deleted_at IS NULL AND ({where_sql})
            ORDER BY rr.imported_at ASC, rr.original_filename ASC
        """), params).mappings().all()
    return [dict(row) for row in rows]


def load_stored_lines(receipt_table_id: str | None) -> list[dict[str, Any]]:
    if not receipt_table_id:
        return []
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT line_index, raw_label, normalized_label, quantity, unit,
                   unit_price, line_total, discount_amount
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id AND COALESCE(is_deleted, 0) = 0
            ORDER BY line_index ASC
        """), {"receipt_table_id": receipt_table_id}).mappings().all()
    output = []
    for row in rows:
        item = dict(row)
        item["signature"] = signature(item.get("raw_label") or item.get("normalized_label"), item.get("line_total"))
        output.append(item)
    return output


def ocr_payload(file_bytes: bytes, filename: str) -> dict[str, Any]:
    paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
    tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
    return {
        "paddle": {"confidence": paddle_confidence, "line_count": len(paddle_lines or []), "lines": paddle_lines or []},
        "tesseract": {"confidence": tesseract_confidence, "line_count": len(tesseract_lines or []), "lines": tesseract_lines or []},
    }


def preprocessed_ocr_payload(file_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        processed_bytes, decision = apply_receipt_image_preprocessing(file_bytes, filename)
    except Exception as exc:
        return {"error": str(exc), "ocr": None}
    route = getattr(decision, "selected_route", None) if decision else None
    return {"preprocessing_route": route, "ocr": ocr_payload(processed_bytes, f"{Path(filename).stem}-preprocessed.png")}


def duplicate_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("sha256_hash") or "")].append(row)
    matrix = []
    for digest, group in grouped.items():
        visible = [row for row in group if row.get("receipt_table_id") and not row.get("receipt_deleted_at")]
        first = visible[0] if visible else group[0]
        for row in group:
            matrix.append({
                "original_filename": row.get("original_filename"),
                "sha256_hash": digest,
                "raw_receipt_id": row.get("raw_receipt_id"),
                "receipt_table_id": row.get("receipt_table_id"),
                "visible_in_kassa": bool(row.get("receipt_table_id") and not row.get("receipt_deleted_at")),
                "duplicate_group_size": len(group),
                "duplicate_of": None if row.get("raw_receipt_id") == first.get("raw_receipt_id") else {
                    "original_filename": first.get("original_filename"),
                    "raw_receipt_id": first.get("raw_receipt_id"),
                    "receipt_table_id": first.get("receipt_table_id"),
                },
                "store_name": row.get("store_name"),
                "purchase_at": row.get("purchase_at"),
                "total_amount": float(dec(row.get("total_amount"))) if row.get("total_amount") is not None else None,
                "parse_status": row.get("parse_status") or row.get("raw_status"),
            })
    return matrix


def analyze(row: dict[str, Any]) -> dict[str, Any]:
    filename = str(row.get("original_filename") or "receipt")
    storage_path = Path(str(row.get("storage_path") or ""))
    receipt_table_id = str(row.get("receipt_table_id") or "") or None
    stored_lines = load_stored_lines(receipt_table_id)
    if not storage_path.exists():
        return {"original_filename": filename, "storage_path": str(storage_path), "storage_exists": False, "stored_lines": stored_lines}
    file_bytes = storage_path.read_bytes()
    mime_type = detect_mime_type(filename, file_bytes, row.get("mime_type"))
    result = parse_receipt_content(file_bytes, filename, mime_type)
    parsed_lines = []
    for index, line in enumerate(result.lines or []):
        trace = line.get("producer_trace") or {}
        parsed_lines.append({
            "line_index": index,
            "raw_label": line.get("raw_label"),
            "normalized_label": line.get("normalized_label"),
            "line_total": line.get("line_total"),
            "source_index": line.get("source_index"),
            "source_raw_line": trace.get("raw_line"),
            "classification": trace.get("classification"),
            "signature": signature(line.get("raw_label") or line.get("normalized_label"), line.get("line_total")),
        })
    parsed_signatures = {line["signature"] for line in parsed_lines}
    stored_signatures = {line["signature"] for line in stored_lines}
    parsed_sum = sum((dec(line.get("line_total")) for line in parsed_lines), Decimal("0.00"))
    stored_sum = sum((dec(line.get("line_total")) for line in stored_lines), Decimal("0.00"))
    total = dec(result.total_amount)
    return {
        "original_filename": filename,
        "raw_receipt_id": row.get("raw_receipt_id"),
        "receipt_table_id": receipt_table_id,
        "sha256_hash": row.get("sha256_hash"),
        "storage_path": str(storage_path),
        "storage_exists": True,
        "raw_ocr": ocr_payload(file_bytes, filename),
        "preprocessed_ocr": preprocessed_ocr_payload(file_bytes, filename),
        "reparsed": {
            "parse_status": result.parse_status,
            "store_name": result.store_name,
            "store_branch": result.store_branch,
            "purchase_at": result.purchase_at,
            "total_amount": float(total) if result.total_amount is not None else None,
            "line_count": len(parsed_lines),
            "line_total_sum": float(parsed_sum),
            "balance_matches": bool(parsed_sum == total),
            "lines": parsed_lines,
        },
        "stored_summary": {"line_count": len(stored_lines), "line_total_sum": float(stored_sum)},
        "stored_lines": stored_lines,
        "diff": {
            "parsed_not_stored": [line for line in parsed_lines if line["signature"] not in stored_signatures],
            "stored_not_parsed": [line for line in stored_lines if line["signature"] not in parsed_signatures],
            "total_minus_stored": float((total - stored_sum).quantize(Decimal("0.01"))),
            "parsed_minus_stored": float((parsed_sum - stored_sum).quantize(Decimal("0.01"))),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", action="append", default=[])
    parser.add_argument("--output", default="reports/m2c2i_jumbo_duplicate_ocr_diagnosis.json")
    args = parser.parse_args()
    filenames = args.filename or DEFAULT_FILENAMES
    rows = load_rows(filenames)
    analyses = []
    seen = set()
    for row in rows:
        filename = str(row.get("original_filename") or "")
        total = dec(row.get("total_amount")) if row.get("total_amount") is not None else Decimal("0.00")
        if filename not in {"Jumbo foto 12.jpeg", "Jumbo foto 14.jpeg"} and total not in {Decimal("30.11"), Decimal("38.80")}:
            continue
        key = row.get("receipt_table_id") or row.get("raw_receipt_id")
        if not key or key in seen:
            continue
        seen.add(key)
        analyses.append(analyze(row))
    report = {
        "name": "M2C2i Jumbo duplicate + raw OCR diagnosis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(rows),
        "duplicate_matrix": duplicate_matrix(rows),
        "analyses": analyses,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False), encoding="utf-8")
    print("M2C2i Jumbo duplicate + raw OCR diagnosis")
    print(f"Report: {output_path}")
    for item in report["duplicate_matrix"]:
        duplicate = item.get("duplicate_of") or {}
        duplicate_label = f" duplicate_of={duplicate.get('original_filename')}" if duplicate else ""
        print(f"- {item.get('original_filename')} hash={str(item.get('sha256_hash') or '')[:12]} table={item.get('receipt_table_id')} visible={item.get('visible_in_kassa')}{duplicate_label}")
    for item in analyses:
        diff = item.get("diff") or {}
        print(f"- {item.get('original_filename')} total_minus_stored={diff.get('total_minus_stored')} parsed_minus_stored={diff.get('parsed_minus_stored')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
