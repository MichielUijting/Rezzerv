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


def parse_decimal(value: object) -> Decimal | None:
    """Parse an OCR amount-like value into a 2-decimal Decimal.

    This helper is deliberately status-neutral: invalid values return None and
    no parser, UI, or PO status is derived here.
    """
    if value is None:
        return None

    cleaned = str(value).strip()
    if not cleaned:
        return None

    cleaned = cleaned.replace('€', '').replace('EUR', '').replace('eur', '').replace('\xa0', ' ').strip()
    cleaned = re.sub(r'[^0-9,.-]', '', cleaned)
    if not cleaned or cleaned in {'-', ',', '.', '-,', '-.'}:
        return None

    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    else:
        cleaned = cleaned.replace(',', '.')

    try:
        return Decimal(cleaned).quantize(Decimal('0.01'))
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
