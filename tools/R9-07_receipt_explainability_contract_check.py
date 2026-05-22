from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPLAINABILITY = ROOT / "backend" / "app" / "receipt_ingestion" / "explainability.py"
SERIALIZER = ROOT / "backend" / "app" / "receipt_ingestion" / "parser_debug_serializer.py"


def fail(message: str) -> None:
    print(f"R9-07 FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"R9-07 OK: {message}")


def main() -> int:
    if not EXPLAINABILITY.exists():
        fail(f"explainability module ontbreekt: {EXPLAINABILITY}")
    text = EXPLAINABILITY.read_text(encoding="utf-8")
    required = [
        "build_receipt_explainability",
        "generic_all_receipts_all_stores",
        "source_route",
        "ocr_route",
        "preprocessing",
        "header_decisions",
        "total_decision",
        "article_decisions",
        "status_explanation",
        "read_only",
    ]
    for marker in required:
        if marker not in text:
            fail(f"explainability marker ontbreekt: {marker}")
    forbidden = ["aldi_only", "force_total", "setattr(result"]
    for marker in forbidden:
        if marker in text:
            fail(f"explainability bevat verboden parsermutatie/specifieke marker: {marker}")
    serializer = SERIALIZER.read_text(encoding="utf-8")
    if "build_receipt_explainability" not in serializer or "'explainability'" not in serializer:
        fail("parser_debug_serializer exporteert explainability niet")
    ok("generic receipt explainability contract is aanwezig")
    ok("parser_debug_serializer neemt explainability op in debug payload")
    ok("R9-07 generic parser explainability is geborgd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())