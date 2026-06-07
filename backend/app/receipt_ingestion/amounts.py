"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


def amount_to_float(value: Decimal | None) -> float | None:
    """Convert Decimal amount to float while preserving None semantics.

    Extracted as a low-risk helper from receipt_service.py.
    This helper is intentionally side-effect free and status-neutral.
    """
    return float(value) if value is not None else None


def parse_quantity(raw: str | None) -> Decimal | None:
    """Parse a quantity-like OCR value into Decimal.

    Examples:
    - '1'
    - '1,5'
    - '2 kg'

    Invalid or empty values return None.
    """
    if not raw:
        return None

    cleaned = raw.strip().replace(',', '.')
    cleaned = re.sub(r'[^0-9\-.]', '', cleaned)
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_decimal(raw: str | None) -> Decimal | None:
    """Parse an OCR amount-like value into a 2-decimal Decimal.

    This is the R7b-16b frozen behavior extracted from receipt_service._parse_decimal.
    The helper is deliberately status-neutral: invalid values return None.
    """
    if not raw:
        return None
    value = raw.replace('€', '').replace('EUR', '').replace('eur', '').strip()
    value = value.replace('.', '').replace(',', '.') if ',' in value and '.' in value else value.replace(',', '.')
    value = re.sub(r'[^0-9\-.]', '', value)
    if not value or value in {'-', '.', '-.'}:
        return None
    try:
        return Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def price_from_split_parts(euros: str | None, cents: str | None) -> Decimal | None:
    """Build a Decimal amount from euro/cents OCR split parts.

    Examples:
    - ('1', '23') -> Decimal('1.23')
    - ('0', '05') -> Decimal('0.05')

    Invalid or incomplete input returns None.
    """
    if euros is None or cents is None:
        return None

    try:
        return Decimal(f"{int(euros)}.{int(cents):02d}").quantize(Decimal('0.01'))
    except Exception:
        return None
