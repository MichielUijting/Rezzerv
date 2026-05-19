from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'

text = SERVICE.read_text(encoding='utf-8')

marker = 'from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal\n'
replacement = """from app.receipt_ingestion.amounts import (
    amount_to_float as _amount_to_float,
    parse_decimal as _parse_decimal,
    parse_quantity as _parse_quantity,
    price_from_split_parts as _price_from_split_parts,
)
"""

if marker not in text:
    raise SystemExit('Expected parse_decimal import marker not found')
text = text.replace(marker, replacement, 1)

helper_blocks = [
    """def _parse_quantity(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(',', '.')
    cleaned = re.sub(r'[^0-9\\-.]', '', cleaned)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


""",
    """def _amount_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


""",
    """def _price_from_split_parts(euros: str | None, cents: str | None) -> Decimal | None:
    if euros is None or cents is None:
        return None
    try:
        return Decimal(f\"{int(euros)}.{int(cents):02d}\").quantize(Decimal('0.01'))
    except Exception:
        return None


""",
]

for block in helper_blocks:
    if block not in text:
        raise SystemExit('Expected helper block not found; aborting to avoid unsafe partial patch')
    text = text.replace(block, '', 1)

SERVICE.write_text(text, encoding='utf-8')
print('R7b-24 patch applied: amount residue helpers wired via receipt_ingestion.amounts import aliases.')
