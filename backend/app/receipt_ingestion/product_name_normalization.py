"""Generic product-name normalization for receipt labels.

This module contains no product-name, brand or retailer knowledge. It only
normalizes generic receipt-label artefacts such as purchase counts, trailing
receipt amounts and isolated OCR/mojibake fragments.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

LEADING_ITEM_COUNT_RE = re.compile(r'^\s*(?P<count>\d{1,4})\s*[x×]\s+(?P<label>.+)$', re.IGNORECASE)
TRAILING_TRANSACTION_COUNT_RE = re.compile(r'^(?P<label>.+?\D)\s+(?P<count>\d{1,4})\s*$')
TRAILING_AMOUNT_RE = re.compile(r'\s+-?\d{1,6}[\.,]\d{2}\s*$')
TRAILING_ORPHAN_RE = re.compile(r'(?:\s+[ÃÂâã€]+)+\s*$', re.IGNORECASE)
GENERIC_EDGE_NOISE_RE = re.compile(r'^[\s\W_]+|[\s\W_]+$')


def _as_number(value: str) -> int | None:
    try:
        number = int(str(value or '').strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _has_letters(value: str | None) -> bool:
    return bool(re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', str(value or '')))


def _financials_confirm_trailing_count(unit_price: Any, line_total: Any, count: int) -> bool:
    unit = _as_decimal(unit_price)
    total = _as_decimal(line_total)
    if unit is None or total is None or unit <= 0 or total <= 0:
        return False
    expected = (unit * Decimal(count)).quantize(Decimal('0.01'))
    actual = total.quantize(Decimal('0.01'))
    return abs(expected - actual) <= Decimal('0.01')


def _transaction_confirms_trailing_count(
    transaction_text: str | None,
    count: int,
    *,
    unit_price: Any = None,
    line_total: Any = None,
) -> bool:
    """Require independent transaction proof before stripping a trailing number.

    A bare product label such as ``iPhone 16`` or ``Vitamine B12`` is never
    changed. Proof can come from an explicit ``N x price`` token in the source
    line, or from exact financial arithmetic ``unit_price * N == line_total``.
    """
    text = re.sub(r'\s+', ' ', str(transaction_text or '')).strip()
    if text and re.search(rf'(?<!\d){count}\s*[x×]\s*\d+[\.,]\d{{2}}(?:\D|$)', text, re.IGNORECASE):
        return True
    return _financials_confirm_trailing_count(unit_price, line_total, count)


def normalize_product_name_label(
    label: str | None,
    quantity: Any = None,
    *,
    transaction_text: str | None = None,
    unit_price: Any = None,
    line_total: Any = None,
) -> tuple[str | None, Any, dict[str, Any] | None]:
    """Normalize generic receipt artefacts from a product label."""
    original = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not original:
        return None, quantity, None

    normalized = original
    detected_quantity = quantity
    applied: list[str] = []
    quantity_from_name_prefix = None
    quantity_from_transaction_suffix = None

    leading_count = LEADING_ITEM_COUNT_RE.match(normalized)
    if leading_count:
        candidate_label = re.sub(r'\s+', ' ', leading_count.group('label')).strip(' .:-')
        count_value = _as_number(leading_count.group('count'))
        if count_value is not None and _has_letters(candidate_label):
            normalized = candidate_label
            detected_quantity = count_value
            quantity_from_name_prefix = count_value
            applied.append('leading_item_count_removed')

    trailing_count = TRAILING_TRANSACTION_COUNT_RE.match(normalized)
    if trailing_count:
        candidate_label = re.sub(r'\s+', ' ', trailing_count.group('label')).strip(' .:-')
        count_value = _as_number(trailing_count.group('count'))
        if (
            count_value is not None
            and _has_letters(candidate_label)
            and _transaction_confirms_trailing_count(
                transaction_text,
                count_value,
                unit_price=unit_price,
                line_total=line_total,
            )
        ):
            normalized = candidate_label
            detected_quantity = count_value
            quantity_from_transaction_suffix = count_value
            applied.append('trailing_transaction_item_count_removed')

    amount_stripped = TRAILING_AMOUNT_RE.sub('', normalized).strip()
    if amount_stripped != normalized and _has_letters(amount_stripped):
        normalized = amount_stripped
        applied.append('trailing_amount_removed')

    orphan_stripped = TRAILING_ORPHAN_RE.sub('', normalized).strip()
    if orphan_stripped != normalized and _has_letters(orphan_stripped):
        normalized = orphan_stripped
        applied.append('trailing_orphan_ocr_fragment_removed')

    edge_stripped = GENERIC_EDGE_NOISE_RE.sub('', normalized).strip()
    if edge_stripped != normalized and _has_letters(edge_stripped):
        normalized = edge_stripped
        applied.append('edge_noise_removed')

    normalized = re.sub(r'\s+', ' ', normalized).strip(' .:-')
    if not normalized or not _has_letters(normalized):
        return original, quantity, None
    if normalized == original and detected_quantity == quantity:
        return normalized, detected_quantity, None
    return normalized, detected_quantity, {
        'original_label': original,
        'normalized_label': normalized,
        'normalization_rules': applied,
        'quantity_from_name_prefix': quantity_from_name_prefix,
        'quantity_from_transaction_suffix': quantity_from_transaction_suffix,
    }
