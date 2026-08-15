"""Generic package extraction for receipt product labels.

This module contains no product-name, brand or retailer knowledge. It recognizes
common package-content patterns while keeping an already detected purchase
quantity authoritative. Package composition is returned as metadata so callers
can persist or expose it without overloading the purchase quantity.
"""

from __future__ import annotations

import re
from typing import Any

PACKAGE_LABEL_RE = re.compile(
    r'(?<![A-Za-z0-9])(?P<quantity>\d+(?:[\.,]\d+)?)\s*(?P<unit>kg|g|gr|gram|ml|cl|l|liter)\b',
    re.IGNORECASE,
)
MULTIPACK_LABEL_RE = re.compile(
    r'(?<![A-Za-z0-9])(?P<count>\d{1,4})\s*[x×]\s*(?P<quantity>\d+(?:[\.,]\d+)?)\s*(?P<unit>kg|g|gr|gram|ml|cl|l|liter)\b',
    re.IGNORECASE,
)

UNIT_NORMALIZATION = {
    'gr': 'g',
    'gram': 'g',
    'liter': 'l',
}


def _as_number(value: str) -> float | int | None:
    try:
        number = float(str(value or '').replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _normalize_unit(value: str | None) -> str | None:
    unit = str(value or '').strip().lower()
    if not unit:
        return None
    return UNIT_NORMALIZATION.get(unit, unit)


def _article_label_without_match(text: str, match: re.Match[str]) -> str:
    return re.sub(r'\s+', ' ', (text[:match.start()] + ' ' + text[match.end():])).strip(' .:-')


def extract_package_from_label(label: str | None) -> dict[str, Any] | None:
    """Extract generic package content/composition from a product label."""
    text = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not text:
        return None

    multipack = MULTIPACK_LABEL_RE.search(text)
    match = multipack or PACKAGE_LABEL_RE.search(text)
    if not match:
        return None

    quantity = _as_number(match.group('quantity'))
    unit = _normalize_unit(match.group('unit'))
    pack_count = _as_number(match.group('count')) if multipack else 1
    if quantity is None or not unit or pack_count is None:
        return None

    article_label = _article_label_without_match(text, match)
    if len(article_label) < 2 or not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', article_label):
        return None

    return {
        'article_label': article_label,
        'package_count': pack_count,
        'package_quantity': quantity,
        'package_unit': unit,
        'package_text': match.group(0),
    }


def apply_package_extraction_to_candidate(
    label: str | None,
    quantity: Any = None,
    unit: str | None = None,
) -> tuple[str | None, Any, str | None, dict[str, Any] | None]:
    """Normalize package text without overwriting an established purchase count.

    Backward compatibility is retained for labels where no purchase quantity was
    detected: package quantity/unit remain the candidate quantity/unit. When a
    purchase quantity already exists (for example ``2 x Pasta 500g``), that
    purchase quantity remains authoritative and package content is available in
    metadata instead of replacing it.
    """
    label_value = re.sub(r'\s+', ' ', str(label or '')).strip()
    existing_unit = str(unit or '').strip() or None
    package = extract_package_from_label(label_value)
    if not package:
        return label_value or None, quantity, existing_unit, None

    if quantity not in (None, ''):
        return package['article_label'], quantity, existing_unit, package
    if existing_unit:
        return package['article_label'], quantity, existing_unit, package
    return package['article_label'], package['package_quantity'], package['package_unit'], package
