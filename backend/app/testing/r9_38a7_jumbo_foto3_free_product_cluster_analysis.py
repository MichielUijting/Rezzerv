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

TARGET_FILENAME = "Jumbo foto 3.jpg"
EXPECTED_TOTAL = Decimal("0.00")
EXPECTED_LINE_COUNT = 1
EXPECTED_GROSS_PRODUCT_AMOUNT = Decimal("1.65")
EXPECTED_COMPENSATION_AMOUNT = Decimal("-1.65")

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

TRAILING_AMOUNT_RE = re.compile(r"(?<!\d)(?P<amount>-?\d{1,4}[\.,]\d{2})(?!\d)\s*$")
FREE_COMPENSATION_RE = re.compile(
    r"^\s*(?P<label>(?:gratis|actie|korting|bonus|voordeel)[A-Za-z0-9À-ÖØ-öø-ÿ .:'/-]*)\s+(?P<amount>-\d{1,4}[\.,]\d{2})\s*$",
    re.IGNORECASE,
)
NON_PRODUCT_LABEL_RE = re.compile(
    r"\b(?:totaal|btw|betaald|bankpas|betaling|terminal|transactie|pasnummer|oude saldo|nieuwe saldo|gespaarde punten|ingewisselde punten|medewerker|store|pos|www|jumbo extra)\b",
    re.IGNORECASE,
)


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
        _normalize_filename("Jumbo foto 3.jpg"),
        _normalize_filename("Jumbo foto 3.jpeg"),
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


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _amount_candidates(text_value: str) -> list[str]:
    return re.findall(r"(?<!\d)(?:-?\d{1,4}[\.,]\d{2})(?!\d)", text_value or "")


def _extract_label_and_amount(value: str | None) -> tuple[str, Decimal] | None:
    text_value = _clean_text(value)
    match = TRAILING_AMOUNT_RE.search(text_value)
    if not match:
        return None
    label = text_value[: match.start()].strip(" .:-")
    amount = _decimal(match.group("amount"))
    if not label or amount <= 0:
        return None
    if NON_PRODUCT_LABEL_RE.search(label):
        return None
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
        return None
    return label, amount


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
    }


def _parsed_by_source(parsed_lines: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    mapped: dict[int, list[dict[str, Any]]] = {}
    for line in parsed_lines:
        if not isinstance(line, dict):
            continue
        source_index = line.get("source_index")
        if isinstance(source_index, int):
            mapped.setdefault(source_index, []).append(line)
    return mapped


def _classified_ocr_line(index: int, text_value: str, parsed_by_source: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "index": index,
        "text": text_value,
        "amount_candidates": _amount_candidates(text_value),
        "classification": classify_receipt_text_line(text_value),
        "parsed_matches": [_line_payload(line) for line in parsed_by_source.get(index, [])],
    }


def _find_free_product_clusters(ocr_lines: list[str], parsed_source_map: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for product_index in range(0, max(len(ocr_lines) - 1, 0)):
        product_payload = _extract_label_and_amount(ocr_lines[product_index])
        if product_payload is None:
            continue
        product_label, product_amount = product_payload

        compensation_index = product_index + 1
        compensation_text = _clean_text(ocr_lines[compensation_index])
        compensation_match = FREE_COMPENSATION_RE.match(compensation_text)
        if not compensation_match:
            continue
        compensation_label = _clean_text(compensation_match.group("label"))
        compensation_amount = _decimal(compensation_match.group("amount"))
        if compensation_amount >= 0:
            continue

        net_total = (product_amount + compensation_amount).quantize(Decimal("0.01"))
        product_key = re.sub(r"[^a-z0-9]+", "", product_label.lower())
        compensation_key = re.sub(r"[^a-z0-9]+", "", compensation_label.lower())
        label_similarity_hint = product_key and any(part and part in compensation_key for part in product_key.split("jumbo"))

        clusters.append(
            {
                "product_index": product_index,
                "product_text": _clean_text(ocr_lines[product_index]),
                "product_label": product_label,
                "product_amount": str(product_amount),
                "compensation_index": compensation_index,
                "compensation_text": compensation_text,
                "compensation_label": compensation_label,
                "compensation_amount": str(compensation_amount),
                "net_cluster_total": str(net_total),
                "net_total_is_zero": net_total == Decimal("0.00"),
                "label_similarity_hint": bool(label_similarity_hint),
                "already_parsed_product_line": bool(parsed_source_map.get(product_index)),
                "already_parsed_compensation_line": bool(parsed_source_map.get(compensation_index)),
                "parsed_product_matches": [_line_payload(line) for line in parsed_source_map.get(product_index, [])],
                "parsed_compensation_matches": [_line_payload(line) for line in parsed_source_map.get(compensation_index, [])],
            }
        )
    return clusters


def main() -> int:
    source_path = _find_source_file(TARGET_FILENAME)
    if source_path is None:
        print(json.dumps({"missing_file": TARGET_FILENAME}, indent=2, ensure_ascii=False))
        return 2

    file_bytes = source_path.read_bytes()
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    result = parse_receipt_content(file_bytes, source_path.name, mime_type)
    parsed_lines = list(getattr(result, "lines", None) or [])
    parsed_source_map = _parsed_by_source(parsed_lines)
    ocr_lines, ocr_confidence = _ocr_image_text_with_paddle(file_bytes, source_path.name)

    clusters = _find_free_product_clusters(ocr_lines, parsed_source_map)
    target_clusters = [
        cluster for cluster in clusters
        if _decimal(cluster.get("product_amount")) == EXPECTED_GROSS_PRODUCT_AMOUNT
        and _decimal(cluster.get("compensation_amount")) == EXPECTED_COMPENSATION_AMOUNT
        and _decimal(cluster.get("net_cluster_total")) == EXPECTED_TOTAL
    ]

    gross_sum = sum((_decimal(line.get("line_total")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    line_discount_sum = sum((_decimal(line.get("discount_amount")) for line in parsed_lines), Decimal("0.00")).quantize(Decimal("0.01"))
    total_amount = _decimal(getattr(result, "total_amount", None))

    ocr_classified = [
        _classified_ocr_line(index, text_value, parsed_source_map)
        for index, text_value in enumerate(ocr_lines)
    ]
    unparsed_amount_lines = [
        line for line in ocr_classified
        if line["amount_candidates"] and not line["parsed_matches"]
    ]

    output = {
        "test": "R9-38A7 Jumbo foto 3 free product cluster analysis",
        "mode": "read_only_gap_analysis",
        "architecture_guardrails": {
            "diagnostics_only": True,
            "production_data_changed": False,
            "parser_changed": False,
            "status_classification_changed": False,
            "functional_status_source": "SSOT only; this script does not calculate po_norm_status_label",
            "no_receipt_specific_rule": "Detects generic free-product clusters: positive priced product followed by free/discount compensation line",
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
        "line_discount_sum": str(line_discount_sum),
        "net_line_sum": str((gross_sum + line_discount_sum).quantize(Decimal("0.01"))),
        "ocr_confidence": ocr_confidence,
        "parsed_source_indexes": sorted(parsed_source_map.keys()),
        "parsed_lines": [_line_payload(line) for line in parsed_lines],
        "free_product_clusters": clusters,
        "target_free_product_clusters": target_clusters,
        "target_cluster_present": bool(target_clusters),
        "target_cluster_explains_zero_total": bool(target_clusters) and all(_decimal(cluster.get("net_cluster_total")) == Decimal("0.00") for cluster in target_clusters),
        "expected_count_if_cluster_collapsed": len(parsed_lines) - 1 if target_clusters and len(parsed_lines) >= 2 else len(parsed_lines),
        "expected_count_matches_baseline_if_collapsed": (len(parsed_lines) - 1) == EXPECTED_LINE_COUNT if target_clusters and len(parsed_lines) >= 2 else len(parsed_lines) == EXPECTED_LINE_COUNT,
        "ocr_lines": ocr_classified,
        "unparsed_amount_lines": unparsed_amount_lines,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("R9-38A7 JUMBO FOTO 3 FREE PRODUCT CLUSTER ANALYSIS COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
