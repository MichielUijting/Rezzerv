from __future__ import annotations

import json
import mimetypes
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.receipt_ingestion.line_classifier import classify_receipt_text_line
from app.receipt_ingestion.service_parts.image_ocr_flow import _ocr_image_text_with_paddle
from app.services.receipt_service import parse_receipt_content

TARGET_FILENAME = "Jumbo App 1.png"
EXPECTED_TOTAL = Decimal("56.91")
EXPECTED_LINE_COUNT = 16

SEARCH_ROOTS = (
    Path.cwd(),
    Path.cwd() / "backend",
    Path.cwd() / "data",
    Path.cwd() / "backend" / "data",
    Path("/app"),
    Path("/app/backend"),
    Path("/app/backend/data"),
    Path("/tmp"),
)

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _normalize_filename(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _find_source_file(filename: str) -> Path | None:
    seen_roots: set[Path] = set()
    target_key = _normalize_filename(filename)
    expected_keys = {
        target_key,
        _normalize_filename("Jumbo app 1.png"),
        _normalize_filename("Jumbo App 1.png"),
    }
    for root in SEARCH_ROOTS:
        try:
            resolved = root.resolve()
        except Exception:
            continue
        if resolved in seen_roots or not resolved.exists():
            continue
        seen_roots.add(resolved)

        try:
            for path in resolved.rglob("*"):
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                if not path.is_file():
                    continue
                if _normalize_filename(path.name) in expected_keys:
                    return path
        except Exception:
            continue
    return None


def _amount_candidates(text: str) -> list[str]:
    return re.findall(r"(?<!\d)(?:-?\d{1,4}[\.,]\d{2})(?!\d)", text or "")


def _line_payload(line: dict[str, Any]) -> dict[str, Any]:
    trace = line.get("producer_trace") if isinstance(line, dict) else None
    if not isinstance(trace, dict):
        trace = {}
    return {
        "source_index": line.get("source_index"),
        "raw_label": line.get("raw_label"),
        "normalized_label": line.get("normalized_label"),
        "quantity": line.get("quantity"),
        "unit": line.get("unit"),
        "unit_price": line.get("unit_price"),
        "line_total": line.get("line_total"),
        "discount_amount": line.get("discount_amount"),
        "trace_function": trace.get("function_name"),
        "trace_branch": trace.get("append_branch"),
        "classification": trace.get("classification"),
        "classification_rule": trace.get("classification_rule"),
        "classification_stage": trace.get("classification_stage"),
        "near_duplicate_consolidated": trace.get("near_duplicate_consolidated"),
    }


def _classified_ocr_line(index: int, text: str, parsed_by_source: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    classification = classify_receipt_text_line(text)
    parsed_matches = parsed_by_source.get(index, [])
    return {
        "index": index,
        "text": text,
        "amount_candidates": _amount_candidates(text),
        "classification": classification,
        "parsed_matches": [_line_payload(line) for line in parsed_matches],
    }


def main() -> int:
    source_path = _find_source_file(TARGET_FILENAME)
    if source_path is None:
        print(json.dumps({"missing_file": TARGET_FILENAME}, indent=2, ensure_ascii=False))
        return 2

    file_bytes = source_path.read_bytes()
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    result = parse_receipt_content(file_bytes, source_path.name, mime_type)
    parsed_lines = list(getattr(result, "lines", None) or [])

    parsed_by_source: dict[int, list[dict[str, Any]]] = {}
    for line in parsed_lines:
        if not isinstance(line, dict):
            continue
        source_index = line.get("source_index")
        if isinstance(source_index, int):
            parsed_by_source.setdefault(source_index, []).append(line)

    ocr_lines, ocr_confidence = _ocr_image_text_with_paddle(file_bytes, source_path.name)
    classified_lines = [
        _classified_ocr_line(index, text, parsed_by_source)
        for index, text in enumerate(ocr_lines)
    ]

    unparsed_amount_lines = [
        line for line in classified_lines
        if line["amount_candidates"] and not line["parsed_matches"]
    ]

    parsed_amount_line_indexes = {
        int(line["source_index"])
        for line in parsed_lines
        if isinstance(line, dict) and isinstance(line.get("source_index"), int)
    }
    parsed_without_paddle_source_match = [
        _line_payload(line) for line in parsed_lines
        if isinstance(line, dict)
        and isinstance(line.get("source_index"), int)
        and int(line["source_index"]) >= len(ocr_lines)
    ]

    gross_sum = sum((_decimal(line.get("line_total")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    line_discount_sum = sum((_decimal(line.get("discount_amount")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    discount_total = getattr(result, "discount_total", None)
    effective_discount = _decimal(discount_total) if discount_total is not None else line_discount_sum
    net_sum = (gross_sum + effective_discount).quantize(Decimal("0.01"))
    total_amount = _decimal(getattr(result, "total_amount", None))

    output = {
        "test": "R9-38A4a Jumbo App 1 live parse gap analysis",
        "mode": "read_only_gap_analysis",
        "architecture_guardrails": {
            "diagnostics_only": True,
            "production_data_changed": False,
            "parser_changed": False,
            "status_classification_changed": False,
            "functional_status_source": "SSOT only; this script does not calculate po_norm_status_label",
        },
        "filename": source_path.name,
        "source_path": str(source_path),
        "mime_type": mime_type,
        "store_name": getattr(result, "store_name", None),
        "parse_status_technical_only": getattr(result, "parse_status", None),
        "expected_total_amount": str(EXPECTED_TOTAL),
        "total_amount": str(total_amount),
        "expected_line_count": EXPECTED_LINE_COUNT,
        "line_count": len(parsed_lines),
        "gross_line_sum": str(gross_sum),
        "discount_total": str(discount_total) if discount_total is not None else None,
        "line_discount_sum": str(line_discount_sum),
        "net_line_sum": str(net_sum),
        "gross_gap_to_expected_total_plus_discount": str(((EXPECTED_TOTAL - effective_discount) - gross_sum).quantize(Decimal("0.01"))),
        "net_gap_to_expected_total": str((EXPECTED_TOTAL - net_sum).quantize(Decimal("0.01"))),
        "line_count_gap": EXPECTED_LINE_COUNT - len(parsed_lines),
        "ocr_confidence": ocr_confidence,
        "parsed_source_indexes": sorted(parsed_amount_line_indexes),
        "parsed_lines": [_line_payload(line) for line in parsed_lines],
        "ocr_lines": classified_lines,
        "unparsed_amount_lines": unparsed_amount_lines,
        "parsed_without_paddle_source_match": parsed_without_paddle_source_match,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("R9-38A4A JUMBO APP 1 GAP ANALYSIS COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
