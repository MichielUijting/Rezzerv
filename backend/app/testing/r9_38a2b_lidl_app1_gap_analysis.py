"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

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

TARGET_FILENAME = "Lidl App 1.png"

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


def _find_source_file(filename: str) -> Path | None:
    seen_roots: set[Path] = set()
    for root in SEARCH_ROOTS:
        try:
            resolved = root.resolve()
        except Exception:
            continue
        if resolved in seen_roots or not resolved.exists():
            continue
        seen_roots.add(resolved)

        direct = resolved / filename
        if direct.is_file():
            return direct

        try:
            for path in resolved.rglob(filename):
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                if path.is_file():
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
        "trace_branch": trace.get("append_branch"),
        "near_duplicate_consolidated": trace.get("near_duplicate_consolidated"),
    }


def _classified_ocr_line(index: int, text: str, parsed_by_source: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    classification = classify_receipt_text_line(text)
    parsed_matches = parsed_by_source.get(index, [])
    return {
        "index": index,
        "text": text,
        "amount_candidates": _amount_candidates(text),
        "classification": getattr(classification, "classification", None),
        "rule_id": getattr(classification, "rule_id", None),
        "stage": getattr(classification, "stage", None),
        "allows_append": getattr(classification, "allows_append", None),
        "parsed_matches": [_line_payload(line) for line in parsed_matches],
    }


def main() -> int:
    source_path = _find_source_file(TARGET_FILENAME)
    if source_path is None:
        print(json.dumps({"missing_file": TARGET_FILENAME}, indent=2, ensure_ascii=False))
        return 2

    file_bytes = source_path.read_bytes()
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    result = parse_receipt_content(file_bytes, TARGET_FILENAME, mime_type)
    parsed_lines = list(getattr(result, "lines", None) or [])

    parsed_by_source: dict[int, list[dict[str, Any]]] = {}
    for line in parsed_lines:
        if not isinstance(line, dict):
            continue
        source_index = line.get("source_index")
        if isinstance(source_index, int):
            parsed_by_source.setdefault(source_index, []).append(line)

    ocr_lines, ocr_confidence = _ocr_image_text_with_paddle(file_bytes, TARGET_FILENAME)
    classified_lines = [
        _classified_ocr_line(index, text, parsed_by_source)
        for index, text in enumerate(ocr_lines)
    ]

    unparsed_amount_lines = [
        line for line in classified_lines
        if line["amount_candidates"] and not line["parsed_matches"]
    ]

    gross_sum = sum((_decimal(line.get("line_total")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    line_discount_sum = sum((_decimal(line.get("discount_amount")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    discount_total = getattr(result, "discount_total", None)
    effective_discount = _decimal(discount_total) if discount_total is not None else line_discount_sum
    net_sum = (gross_sum + effective_discount).quantize(Decimal("0.01"))
    total_amount = _decimal(getattr(result, "total_amount", None))

    output = {
        "test": "R9-38A2b Lidl App 1 live parse gap analysis",
        "mode": "read_only_gap_analysis",
        "parser_changed": False,
        "status_classification_changed": False,
        "filename": TARGET_FILENAME,
        "source_path": str(source_path),
        "mime_type": mime_type,
        "store_name": getattr(result, "store_name", None),
        "parse_status": getattr(result, "parse_status", None),
        "total_amount": str(total_amount),
        "line_count": len(parsed_lines),
        "gross_line_sum": str(gross_sum),
        "discount_total": str(discount_total) if discount_total is not None else None,
        "line_discount_sum": str(line_discount_sum),
        "net_line_sum": str(net_sum),
        "gross_gap_to_total_plus_discount": str(((total_amount - effective_discount) - gross_sum).quantize(Decimal("0.01"))),
        "net_gap_to_total": str((total_amount - net_sum).quantize(Decimal("0.01"))),
        "ocr_confidence": ocr_confidence,
        "parsed_lines": [_line_payload(line) for line in parsed_lines],
        "ocr_lines": classified_lines,
        "unparsed_amount_lines": unparsed_amount_lines,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("R9-38A2B LIDL APP 1 GAP ANALYSIS COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
