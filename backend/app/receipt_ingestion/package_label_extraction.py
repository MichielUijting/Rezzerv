"""
Generic package extraction for receipt product labels.

This module contains no product-name knowledge. It only recognizes common
quantity + unit patterns that appear inside receipt labels, such as 500g,
1.0 L, 250 ml, 400 g or 1 kg.
"""

from __future__ import annotations

import re
from typing import Any

PACKAGE_LABEL_RE = re.compile(
    r'(?<![A-Za-z0-9])(?P<quantity>\d+(?:[\.,]\d+)?)\s*(?P<unit>kg|g|gr|gram|ml|cl|l|liter)\b',
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


def extract_package_from_label(label: str | None) -> dict[str, Any] | None:
    """Extract a generic package quantity/unit from a product label."""
    text = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not text:
        return None
    match = PACKAGE_LABEL_RE.search(text)
    if not match:
        return None
    quantity = _as_number(match.group('quantity'))
    unit = _normalize_unit(match.group('unit'))
    if quantity is None or not unit:
        return None
    article_label = re.sub(r'\s+', ' ', (text[:match.start()] + ' ' + text[match.end():])).strip(' .:-')
    if len(article_label) < 2 or not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', article_label):
        return None
    return {
        'article_label': article_label,
        'package_quantity': quantity,
        'package_unit': unit,
        'package_text': match.group(0),
    }


def apply_package_extraction_to_candidate(
    label: str | None,
    quantity: Any = None,
    unit: str | None = None,
) -> tuple[str | None, Any, str | None, dict[str, Any] | None]:
    """
    Return label, quantity and unit after generic package extraction.

    Extraction only applies when the parser did not already provide a unit and
    did not already provide a meaningful package quantity/unit pair.
    """
    label_value = re.sub(r'\s+', ' ', str(label or '')).strip()
    existing_unit = str(unit or '').strip() or None
    if existing_unit:
        return label_value or None, quantity, existing_unit, None
    package = extract_package_from_label(label_value)
    if not package:
        return label_value or None, quantity, existing_unit, None
    return package['article_label'], package['package_quantity'], package['package_unit'], package
