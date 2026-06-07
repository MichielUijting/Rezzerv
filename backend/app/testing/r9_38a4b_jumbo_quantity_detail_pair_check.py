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

NON_PRODUCT_LABEL_RE = re.compile(
    r"\b(?:koopzegel|koopzegels|totaal|btw|korting|saldo|punten|extra|gespaard|ingewisseld|bedrag|dinsdag|maandag|woensdag|donderdag|vrijdag|zaterdag|zondag)\b",
    re.IGNORECASE,
)
QUANTITY_DETAIL_RE = re.compile(
    r"^\s*(?P<quantity>\d+(?:[\.,]\d+)?)\s*[xX]\s*(?P<unit_price>\d{1,4}[\.,]\d{2})\s+(?P<line_total>\d{1,4}[\.,]\d{2})\s*$"
)
TRAILING_AMOUNT_RE = re.compile(r"(?<!\d)(?P<amount>\d{1,4}[\.,]\d{2})(?!\d)\s*$")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _normalize_filename(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _find_source_file(filename: str) -> Path | None:
    seen_roots: set[Path] = set()
    expected_keys = {
        _normalize_filename(filename),
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
                if path.is_file() and _normalize_filename(path.name) in expected_keys:
                    return path
        except Exception:
            continue
    return None


def _clean_product_label(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .:-")


def _looks_like_product_label_without_amount(text: str) -> bool:
    label = _clean_product_label(text)
    if not label:
        return False
    if TRAILING_AMOUNT_RE.search(label):
        return False
    if QUANTITY_DETAIL_RE.match(label):
        return False
    if NON_PRODUCT_LABEL_RE.search(label):
        return False
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
        return False
    if len(label) < 3:
        return False
    return True


def _line_payload(line: dict[str, Any]) -> dict[str, Any]:
    trace = line.get("producer_trace") if isinstance(line, dict) else None
    if not isinstance(trace, dict):
        trace = {}
    return {
        "source_index": line.get("source_index"),
        "raw_label": line.get("raw_label"),
        "normalized_label": line.get("normalized_label"),
        "quantity": line.get("quantity"),
        "unit_price": line.get("unit_price"),
        "line_total": line.get("line_total"),
        "trace_branch": trace.get("append_branch"),
        "near_duplicate_consolidated": trace.get("near_duplicate_consolidated"),
    }


def _find_quantity_detail_pairs(ocr_lines: list[str]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index in range(1, len(ocr_lines)):
        detail_text = ocr_lines[index]
        match = QUANTITY_DETAIL_RE.match(detail_text or "")
        if not match:
            continue
        label_index = index - 1
        label_text = ocr_lines[label_index]
        accepted_label = _looks_like_product_label_without_amount(label_text)
        quantity = _decimal(match.group("quantity"))
        unit_price = _decimal(match.group("unit_price"))
        line_total = _decimal(match.group("line_total"))
        calculated_total = (quantity * unit_price).quantize(Decimal("0.01"))
        pairs.append(
            {
                "label_index": label_index,
                "label_text": label_text,
                "detail_index": index,
                "detail_text": detail_text,
                "quantity": str(quantity.normalize()),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
                "calculated_total": str(calculated_total),
                "quantity_total_matches": calculated_total == line_total,
                "accepted_product_label_candidate": accepted_label,
                "excluded_reason": None if accepted_label else "previous_line_not_safe_product_label",
            }
        )
    return pairs


def main() -> int:
    source_path = _find_source_file(TARGET_FILENAME)
    if source_path is None:
        print(json.dumps({"missing_file": TARGET_FILENAME}, indent=2, ensure_ascii=False))
        return 2

    file_bytes = source_path.read_bytes()
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    result = parse_receipt_content(file_bytes, source_path.name, mime_type)
    parsed_lines = list(getattr(result, "lines", None) or [])
    ocr_lines, ocr_confidence = _ocr_image_text_with_paddle(file_bytes, source_path.name)

    parsed_by_source = {
        int(line["source_index"]): _line_payload(line)
        for line in parsed_lines
        if isinstance(line, dict) and isinstance(line.get("source_index"), int)
    }
    quantity_detail_pairs = _find_quantity_detail_pairs(ocr_lines)
    accepted_pairs = [pair for pair in quantity_detail_pairs if pair["accepted_product_label_candidate"]]
    excluded_pairs = [pair for pair in quantity_detail_pairs if not pair["accepted_product_label_candidate"]]

    gross_sum = sum((_decimal(line.get("line_total")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    accepted_pair_total = sum((_decimal(pair["line_total"]) for pair in accepted_pairs), Decimal("0.00")).quantize(Decimal("0.01"))
    expected_gap = (EXPECTED_TOTAL - gross_sum).quantize(Decimal("0.01"))

    output = {
        "test": "R9-38A4b Jumbo app quantity-detail pair gap-check",
        "mode": "read_only_gap_check",
        "architecture_guardrails": {
            "diagnostics_only": True,
            "production_data_changed": False,
            "parser_changed": False,
            "status_classification_changed": False,
            "functional_status_source": "SSOT only; this script does not calculate po_norm_status_label",
            "store_specific_interpretation": "Jumbo app pair pattern is diagnosed here but not integrated into parser output",
        },
        "filename": source_path.name,
        "source_path": str(source_path),
        "mime_type": mime_type,
        "store_name": getattr(result, "store_name", None),
        "parse_status_technical_only": getattr(result, "parse_status", None),
        "expected_total_amount": str(EXPECTED_TOTAL),
        "expected_line_count": EXPECTED_LINE_COUNT,
        "line_count": len(parsed_lines),
        "gross_line_sum": str(gross_sum),
        "gap_to_expected_total": str(expected_gap),
        "ocr_confidence": ocr_confidence,
        "parsed_lines_by_source_index": parsed_by_source,
        "quantity_detail_pairs": quantity_detail_pairs,
        "accepted_pair_candidates": accepted_pairs,
        "excluded_pair_candidates": excluded_pairs,
        "accepted_pair_total": str(accepted_pair_total),
        "gap_after_accepted_pairs": str((expected_gap - accepted_pair_total).quantize(Decimal("0.01"))),
        "expected_target_candidates_present": {
            "Kipdij Reepje 400 + 2 X 5,69 11,38": any(
                pair["label_text"] == "Kipdij Reepje 400" and pair["detail_text"] == "2 X 5,69 11,38" and pair["accepted_product_label_candidate"]
                for pair in quantity_detail_pairs
            ),
            "Coni Kroepoek Bali + 2 X 1,50 3,00": any(
                pair["label_text"] == "Coni Kroepoek Bali" and pair["detail_text"] == "2 X 1,50 3,00" and pair["accepted_product_label_candidate"]
                for pair in quantity_detail_pairs
            ),
            "Koopzegel Digitaal + 51 X 0,10 5,10 excluded": any(
                pair["label_text"] == "Koopzegel Digitaal" and pair["detail_text"] == "51 X 0,10 5,10" and not pair["accepted_product_label_candidate"]
                for pair in quantity_detail_pairs
            ),
        },
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("R9-38A4B JUMBO QUANTITY-DETAIL PAIR GAP CHECK COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
