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

TARGET_FILENAME = "Jumbo foto 1.jpeg"
EXPECTED_TOTAL = Decimal("22.82")
EXPECTED_LINE_COUNT = 7
EXPECTED_CURRENT_STORED_SUM = Decimal("15.32")
EXPECTED_GAP = Decimal("7.50")

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

QUANTITY_DETAIL_RE = re.compile(
    r"^\s*(?P<quantity>\d+(?:[\.,]\d+)?)\s*[xX]\s*(?P<unit_price>\d{1,4}[\.,]\d{2})(?:\s+(?P<line_total>\d{1,4}[\.,]\d{2}))?.*$",
    re.IGNORECASE,
)
DISCOUNT_RE = re.compile(
    r"^\s*(?P<label>(?:actie|korting|bonus|gratis|voordeel)[A-Za-z0-9À-ÖØ-öø-ÿ .:'/-]*)\s+(?P<amount>-\d{1,4}[\.,]\d{2})\s*$",
    re.IGNORECASE,
)
TRAILING_AMOUNT_RE = re.compile(r"(?<!\d)(?P<amount>-?\d{1,4}[\.,]\d{2})(?!\d)\s*$")
NON_PRODUCT_LABEL_RE = re.compile(
    r"\b(?:totaal|betaald|vpay|v-pay|bankpas|betaling|terminal|transactie|btw|merchant|periode|kaart|akkoord|privacy|openingstijden|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|bedankt|tot ziens|medewerker|store|pos|kopie|kaarthouder)\b",
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
        _normalize_filename("Jumbo foto 1.jpeg"),
        _normalize_filename("Jumbo foto 1.jpg"),
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


def _safe_product_label_without_amount(value: str | None) -> bool:
    label = _clean_text(value)
    if len(label) < 3:
        return False
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
        return False
    if TRAILING_AMOUNT_RE.search(label):
        return False
    if QUANTITY_DETAIL_RE.match(label):
        return False
    if DISCOUNT_RE.match(label):
        return False
    if NON_PRODUCT_LABEL_RE.search(label):
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


def _find_paper_clusters(ocr_lines: list[str], parsed_by_source: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for label_index in range(0, max(len(ocr_lines) - 1, 0)):
        label_text = _clean_text(ocr_lines[label_index])
        detail_index = label_index + 1
        detail_text = _clean_text(ocr_lines[detail_index])
        detail_match = QUANTITY_DETAIL_RE.match(detail_text)
        if not detail_match:
            continue
        if not _safe_product_label_without_amount(label_text):
            continue

        quantity = _decimal(detail_match.group("quantity"))
        unit_price = _decimal(detail_match.group("unit_price"))
        line_total = _decimal(detail_match.group("line_total")) if detail_match.group("line_total") else (quantity * unit_price).quantize(Decimal("0.01"))
        calculated_total = (quantity * unit_price).quantize(Decimal("0.01"))

        discount_index = detail_index + 1
        discount_text = _clean_text(ocr_lines[discount_index]) if discount_index < len(ocr_lines) else ""
        discount_match = DISCOUNT_RE.match(discount_text)
        discount_amount = _decimal(discount_match.group("amount")) if discount_match else Decimal("0.00")
        net_cluster_total = (line_total + discount_amount).quantize(Decimal("0.01"))

        clusters.append(
            {
                "label_index": label_index,
                "label_text": label_text,
                "detail_index": detail_index,
                "detail_text": detail_text,
                "quantity": str(quantity.normalize()),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
                "calculated_total": str(calculated_total),
                "quantity_total_matches": abs(calculated_total - line_total) <= Decimal("0.01"),
                "discount_index": discount_index if discount_match else None,
                "discount_text": discount_text if discount_match else None,
                "discount_amount": str(discount_amount),
                "net_cluster_total": str(net_cluster_total),
                "already_parsed_detail_line": bool(parsed_by_source.get(detail_index)),
                "already_parsed_discount_line": bool(parsed_by_source.get(discount_index)) if discount_match else False,
                "parsed_detail_matches": [_line_payload(line) for line in parsed_by_source.get(detail_index, [])],
                "parsed_discount_matches": [_line_payload(line) for line in parsed_by_source.get(discount_index, [])] if discount_match else [],
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

    clusters = _find_paper_clusters(ocr_lines, parsed_source_map)
    target_clusters = [
        cluster for cluster in clusters
        if cluster["label_text"].lower().startswith("kipblokje")
        or "kip" in str(cluster.get("discount_text") or "").lower()
    ]
    target_net_total = sum((_decimal(cluster["net_cluster_total"]) for cluster in target_clusters), Decimal("0.00")).quantize(Decimal("0.01"))

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
        "test": "R9-38A6a Jumbo foto 1 paper-cluster gap analysis",
        "mode": "read_only_gap_analysis",
        "architecture_guardrails": {
            "diagnostics_only": True,
            "production_data_changed": False,
            "parser_changed": False,
            "status_classification_changed": False,
            "functional_status_source": "SSOT only; this script does not calculate po_norm_status_label",
            "no_receipt_specific_rule": "Detects generic Jumbo paper receipt clusters: label, quantity-detail, optional discount line",
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
        "gap_to_expected_total": str((EXPECTED_TOTAL - gross_sum).quantize(Decimal("0.01"))),
        "expected_current_stored_sum": str(EXPECTED_CURRENT_STORED_SUM),
        "expected_gap_from_stored_baseline": str(EXPECTED_GAP),
        "ocr_confidence": ocr_confidence,
        "parsed_source_indexes": sorted(parsed_source_map.keys()),
        "parsed_lines": [_line_payload(line) for line in parsed_lines],
        "paper_quantity_discount_clusters": clusters,
        "target_kip_discount_clusters": target_clusters,
        "target_kip_discount_cluster_total": str(target_net_total),
        "target_cluster_explains_known_gap": target_net_total == EXPECTED_GAP,
        "expected_target_cluster_present": any(
            cluster["label_text"].upper().startswith("KIPBLOKJE")
            and cluster["detail_text"].replace(".", ",").find("2 X 4,99") >= 0
            and cluster.get("discount_text") is not None
            and _decimal(cluster.get("discount_amount")) == Decimal("-2.48")
            for cluster in clusters
        ),
        "ocr_lines": ocr_classified,
        "unparsed_amount_lines": unparsed_amount_lines,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("R9-38A6A JUMBO FOTO 1 PAPER CLUSTER GAP ANALYSIS COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
