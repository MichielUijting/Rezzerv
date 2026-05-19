from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend" / "app" / "services" / "receipt_service.py"

text = SERVICE.read_text(encoding="utf-8")

marker = "from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal\n"

replacement = """from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.fingerprints import (
    _build_receipt_fingerprint,
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
    _normalize_fingerprint_text,
    build_receipt_fingerprint_from_parse_result,
)
"""

if marker not in text:
    raise SystemExit("Expected amounts import marker not found")

text = text.replace(marker, replacement, 1)

helpers = [
    "def _normalize_fingerprint_text(value: Any) -> str:",
    "def _is_plausible_purchase_at(value: str | None) -> bool:",
    "def _is_plausible_total_amount(value: Decimal | None) -> bool:",
    "def _build_receipt_fingerprint(store_name: str | None, purchase_at: str | None, total_amount: Decimal | None, lines: list[dict[str, Any]]) -> str:",
    "def build_receipt_fingerprint_from_parse_result(parse_result: ReceiptParseResult | None) -> str:",
]

for helper in helpers:
    start = text.find(helper)
    if start == -1:
        raise SystemExit(f"Helper not found: {helper}")

    next_def = text.find("\ndef ", start + 1)
    if next_def == -1:
        raise SystemExit(f"Could not determine end of helper: {helper}")

    text = text[:start] + text[next_def + 1:]

SERVICE.write_text(text, encoding="utf-8")

print("R7b-20 fingerprint helper extraction patch applied.")
