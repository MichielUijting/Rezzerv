"""Source-evidence runner voor M2C2i-AH-Photo-04b.

Doel: AH foto 10 regel/prijs-koppeling herstellen zonder blind te patchen.

Deze runner wijzigt geen database. Hij:
- leest de ruwe AH foto 10 uit de bestaande database;
- draait dezelfde image-preprocessing als de runtime;
- print Paddle- en Tesseract-bronregels op de preprocessing-route;
- print ook originele Paddle/Tesseract-regels wanneer preprocessing bytes wijzigt;
- draait parse_receipt_content en print de uiteindelijke regels/diagnostics;
- berekent de Variant-B-financiële diagnose.

Herkenbare output:

AH_PHOTO_10_SOURCE_EVIDENCE_READY
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import (
    apply_receipt_image_preprocessing,
)
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
    get_last_paddle_bbox_payload,
)
from app.services.receipt_service import parse_receipt_content


ENGINE_URL = "sqlite:////app/data/rezzerv.db"
AH_PHOTO_10_ID = "800894a1cf4a48598f4095be5532dc26"
CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal("0.00")
        return Decimal(str(value)).quantize(CENT)
    except Exception:
        return Decimal("0.00")


def print_lines(title: str, lines: list[str] | None) -> None:
    print("")
    print(f"=== {title} ===")
    for idx, line in enumerate(lines or []):
        print(f"{idx:03d}: {line}")


def line_sum(lines: list[dict[str, Any]] | None) -> tuple[Decimal, Decimal]:
    total = sum((money(line.get("line_total")) for line in (lines or [])), Decimal("0.00"))
    discount = sum((money(line.get("discount_amount")) for line in (lines or [])), Decimal("0.00"))
    return total.quantize(CENT), discount.quantize(CENT)


def print_parse_result(result: Any) -> None:
    print("")
    print("=== PARSE RESULT ===")
    print("is_receipt       :", getattr(result, "is_receipt", None))
    print("parse_status     :", getattr(result, "parse_status", None))
    print("confidence_score :", getattr(result, "confidence_score", None))
    print("store_name       :", getattr(result, "store_name", None))
    print("store_branch     :", getattr(result, "store_branch", None))
    print("purchase_at      :", getattr(result, "purchase_at", None))
    print("total_amount     :", getattr(result, "total_amount", None))
    print("discount_total   :", getattr(result, "discount_total", None))
    print("currency         :", getattr(result, "currency", None))

    lines = getattr(result, "lines", None) or []
    line_total, line_discount = line_sum(lines)
    receipt_discount = money(getattr(result, "discount_total", None))
    expected = money(getattr(result, "total_amount", None))
    using_line_discount = (line_total + line_discount).quantize(CENT)
    using_receipt_discount = (line_total + receipt_discount).quantize(CENT)
    using_both = (line_total + line_discount + receipt_discount).quantize(CENT)

    print("line_count       :", len(lines))
    print("line_total_sum   :", line_total)
    print("line_discount_sum:", line_discount)
    print("receipt_discount :", receipt_discount)
    print("variant_b_line   :", using_line_discount)
    print("variant_b_receipt:", using_receipt_discount)
    print("unsafe_both      :", using_both)
    print("diff_line        :", (using_line_discount - expected).quantize(CENT))
    print("diff_receipt     :", (using_receipt_discount - expected).quantize(CENT))
    print("diff_both        :", (using_both - expected).quantize(CENT))

    print("")
    print("--- parsed lines ---")
    for idx, line in enumerate(lines):
        trace = line.get("producer_trace") if isinstance(line, dict) else None
        print(
            idx,
            "| raw=", line.get("raw_label"),
            "| norm=", line.get("normalized_label"),
            "| qty=", line.get("quantity"),
            "| unit_price=", line.get("unit_price"),
            "| line_total=", line.get("line_total"),
            "| discount=", line.get("discount_amount"),
            "| source_index=", line.get("source_index"),
            "| trace_raw=", (trace or {}).get("raw_line") if isinstance(trace, dict) else None,
        )

    print("")
    print("--- parser diagnostics ---")
    print(json.dumps(getattr(result, "parser_diagnostics", None) or {}, indent=2, sort_keys=True, default=str))


def main() -> None:
    engine = create_engine(ENGINE_URL, future=True)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rr.id AS raw_receipt_id,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rr.sha256_hash,
                    rt.total_amount,
                    rt.parse_status
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.id = :id OR rr.id = :id
                LIMIT 1
                """
            ),
            {"id": AH_PHOTO_10_ID},
        ).mappings().first()

    if not row:
        print("AH foto 10 niet gevonden")
        print("AH_PHOTO_10_SOURCE_EVIDENCE_READY")
        print("SOURCE_EVIDENCE_STATUS=DATA_NOT_FOUND")
        return

    print("=== SOURCE RECORD ===")
    for key, value in dict(row).items():
        print(f"{key:18}:", value)

    file_path = Path(row["storage_path"])
    file_bytes = file_path.read_bytes()
    filename = str(row["original_filename"] or file_path.name)
    mime_type = str(row["mime_type"] or "image/jpeg")

    print("")
    print("=== PREPROCESSING ===")
    try:
        preprocessed_bytes, decision = apply_receipt_image_preprocessing(file_bytes, filename)
        route = getattr(decision, "selected_route", None) if decision else None
        print("selected_route      :", route)
        print("bytes_changed       :", preprocessed_bytes != file_bytes)
    except Exception as exc:
        print("preprocessing_error :", repr(exc))
        preprocessed_bytes = file_bytes
        route = None

    ocr_filename = filename
    if route and route != "original":
        ocr_filename = f"{Path(filename).stem}-safe-rotation.png"

    paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(preprocessed_bytes, ocr_filename)
    paddle_bbox_payload = get_last_paddle_bbox_payload(ocr_filename) or {}
    tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(preprocessed_bytes, ocr_filename)

    print("")
    print("=== OCR CONFIDENCE ===")
    print("paddle_confidence   :", paddle_confidence)
    print("tesseract_confidence:", tesseract_confidence)
    print("paddle_bbox_texts   :", len(paddle_bbox_payload.get("texts") or []))
    print("paddle_bbox_boxes   :", len(paddle_bbox_payload.get("boxes") or []))

    print_lines("PREPROCESSED PADDLE LINES", paddle_lines)
    print_lines("PREPROCESSED TESSERACT LINES", tesseract_lines)

    if preprocessed_bytes != file_bytes:
        original_paddle_lines, original_paddle_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
        original_tesseract_lines, original_tesseract_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
        print("")
        print("=== ORIGINAL OCR CONFIDENCE ===")
        print("original_paddle_confidence   :", original_paddle_confidence)
        print("original_tesseract_confidence:", original_tesseract_confidence)
        print_lines("ORIGINAL PADDLE LINES", original_paddle_lines)
        print_lines("ORIGINAL TESSERACT LINES", original_tesseract_lines)

    result = parse_receipt_content(file_bytes, filename, mime_type)
    print_parse_result(result)

    print("")
    print("AH_PHOTO_10_SOURCE_EVIDENCE_READY")
    print("SOURCE_EVIDENCE_STATUS=OK")


if __name__ == "__main__":
    main()
