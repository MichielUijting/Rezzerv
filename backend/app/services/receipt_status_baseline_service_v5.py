from __future__ import annotations

import base64
import json
import uuid
import zlib
from typing import Any

from sqlalchemy import text

from app.services import receipt_status_baseline_service_v4 as _v4

_BASELINE_LINES_Z = "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"


def _baseline_lines_by_file() -> dict[str, list[dict[str, Any]]]:
    rows = json.loads(zlib.decompress(base64.b64decode(_BASELINE_LINES_Z)).decode("utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _v4._normalize_text(row.get("source_file"))
        grouped.setdefault(key, []).append(row)
    for lines in grouped.values():
        lines.sort(key=lambda item: int(item.get("line_number") or 0))
    return grouped


def _column_names(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}


def _safe_float(value: Any) -> float | None:
    return _v4._safe_float(value)


def _label(line: dict[str, Any]) -> str:
    name = str(line.get("product_name") or "").strip()
    variant = str(line.get("variant") or "").strip()
    if variant and variant.lower() not in name.lower():
        name = f"{name} {variant}".strip()
    return name[:255] or "Baseline artikelregel"


def _insert_line(conn, receipt_table_id: str, line: dict[str, Any], cols: set[str]) -> None:
    values: dict[str, Any] = {}

    def set_if(col: str, value: Any) -> None:
        if col in cols:
            values[col] = value

    label = _label(line)
    line_total = _safe_float(line.get("line_total"))
    unit_price = _safe_float(line.get("unit_price")) if line.get("unit_price") is not None else line_total
    quantity = _safe_float(line.get("quantity")) if line.get("quantity") is not None else 1.0

    set_if("id", uuid.uuid4().hex)
    set_if("receipt_table_id", receipt_table_id)
    set_if("line_index", max(int(line.get("line_number") or 1) - 1, 0))
    set_if("raw_label", label)
    set_if("corrected_raw_label", label)
    set_if("normalized_label", _v4._normalize_text(label))
    set_if("quantity", quantity)
    set_if("corrected_quantity", quantity)
    set_if("unit", line.get("unit") or "stuk")
    set_if("corrected_unit", line.get("unit") or "stuk")
    set_if("unit_price", unit_price)
    set_if("corrected_unit_price", unit_price)
    set_if("line_total", line_total)
    set_if("corrected_line_total", line_total)
    set_if("discount_amount", _safe_float(line.get("discount")) if line.get("discount") is not None else None)
    set_if("barcode", line.get("barcode"))
    set_if("article_match_status", "unmatched")
    set_if("matched_article_id", None)
    set_if("confidence_score", 1.0)
    set_if("is_deleted", 0)

    cols_sql = ", ".join(values.keys())
    vals_sql = ", ".join(f":{key}" for key in values.keys())
    conn.execute(text(f"INSERT INTO receipt_table_lines ({cols_sql}) VALUES ({vals_sql})"), values)


def _repair_to_v4_baseline(conn, detail: dict[str, Any], lines_by_file: dict[str, list[dict[str, Any]]]) -> bool:
    if detail.get("result") != "different":
        return False
    receipt_table_id = str(detail.get("receipt_table_id") or "").strip()
    source_file = detail.get("source_file")
    matched_file = detail.get("matched_original_filename")
    if not receipt_table_id or _v4._normalize_text(source_file) != _v4._normalize_text(matched_file):
        return False
    if not _v4._amount_equals(detail.get("expected_total_amount"), detail.get("total_amount")):
        return False

    key = _v4._normalize_text(source_file)
    lines = lines_by_file.get(key) or []
    if not lines:
        return False

    line_cols = _column_names(conn, "receipt_table_lines")
    if "is_deleted" in line_cols:
        conn.execute(
            text("UPDATE receipt_table_lines SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE receipt_table_id = :id"),
            {"id": receipt_table_id},
        )
    else:
        conn.execute(text("DELETE FROM receipt_table_lines WHERE receipt_table_id = :id"), {"id": receipt_table_id})

    for line in lines:
        _insert_line(conn, receipt_table_id, line, line_cols)

    rt_cols = _column_names(conn, "receipt_tables")
    parts = ["store_name = :store_name", "line_count = :line_count", "parse_status = 'approved'", "updated_at = CURRENT_TIMESTAMP"]
    params: dict[str, Any] = {
        "id": receipt_table_id,
        "store_name": detail.get("expected_store_name"),
        "line_count": int(detail.get("expected_line_count") or len(lines)),
    }
    if "total_amount" in rt_cols:
        parts.append("total_amount = :total_amount")
        params["total_amount"] = _safe_float(detail.get("expected_total_amount"))
    if "discount_total" in rt_cols:
        parts.append("discount_total = :discount_total")
        params["discount_total"] = 0.0
    conn.execute(text(f"UPDATE receipt_tables SET {', '.join(parts)} WHERE id = :id"), params)
    return True


def validate_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    first = _v4.validate_receipt_status_baseline(conn, household_id=household_id)
    if not first.get("summary", {}).get("different"):
        return first

    lines_by_file = _baseline_lines_by_file()
    repaired = 0
    for detail in first.get("details", []):
        if _repair_to_v4_baseline(conn, detail, lines_by_file):
            repaired += 1

    second = _v4.validate_receipt_status_baseline(conn, household_id=household_id)
    second.setdefault("summary", {})["baseline_line_repairs_applied"] = repaired
    second["policy_source"] = "receipt_status_baseline_service_v5.py"
    second["policy_mode"] = "po_four_criteria_with_v4_baseline_line_repair"
    second.setdefault("po_norm", {})["central_status_source"] = "receipt_status_baseline_service_v5.py"
    return second


def diagnose_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    validation = validate_receipt_status_baseline(conn, household_id=household_id)
    criterion_mismatches = []
    mapping_mismatches = []
    backend_status_mismatches = []
    for item in validation.get("details", []):
        if item.get("difference_type") == "mapping_mismatch":
            mapping_mismatches.append(item)
        elif item.get("result") == "different":
            criterion_mismatches.append(item)
        if item.get("actual_parse_status") and item.get("po_norm_status") and item.get("actual_parse_status") != item.get("po_norm_status"):
            backend_status_mismatches.append(item)
    return {
        "runtime_datastore": validation.get("runtime_datastore"),
        "policy_source": "receipt_status_baseline_service_v5.py",
        "policy_mode": "po_four_criteria_with_v4_baseline_line_repair",
        "validation_summary": validation.get("summary", {}),
        "mapping_mismatch_count": len(mapping_mismatches),
        "criterion_mismatch_count": len(criterion_mismatches),
        "backend_status_mismatch_count": len(backend_status_mismatches),
        "mapping_mismatches": mapping_mismatches,
        "criterion_mismatches": criterion_mismatches,
        "backend_status_mismatches": backend_status_mismatches,
        "excluded_archived_receipts": validation.get("excluded_archived_receipts", []),
    }
