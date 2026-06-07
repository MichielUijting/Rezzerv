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

from decimal import Decimal
from typing import Any

def _is_jumbo_store_context(store_name: str | None, text_lines: list[str] | None = None) -> bool:
    haystack = ' '.join([str(store_name or ''), *(str(line or '') for line in (text_lines or [])[:30])]).lower()
    return 'jumbo' in haystack

def _jumbo_remove_duplicate_receipt_discount(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
) -> tuple[Decimal | None, dict[str, Any] | None]:
    """Prevent Jumbo discount double counting.

    Jumbo receipts may contain both article-level action lines, e.g.
    ACTIE KIP -2,48, and a summary line Totaal korting: -2,48.
    If the action amount is already attached to article lines as discount_amount,
    the same amount must not remain in receipt-level discount_total.
    """
    if not _is_jumbo_store_context(store_name, text_lines):
        return discount_total, None

    if discount_total is None:
        return None, None

    line_discount_sum = sum(
        (
            Decimal(str(line.get('discount_amount') or 0))
            for line in (lines or [])
            if isinstance(line, dict)
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    receipt_discount = Decimal(str(discount_total or 0)).quantize(Decimal('0.01'))

    if line_discount_sum != Decimal('0.00') and abs(line_discount_sum - receipt_discount) <= Decimal('0.01'):
        return None, {
            'r9_38d5_jumbo_discount_deduplication': {
                'applied': True,
                'line_discount_sum': float(line_discount_sum),
                'receipt_discount_before': float(receipt_discount),
                'receipt_discount_after': 0.0,
                'double_counting_prevented': True,
                'scope': 'Jumbo profile runtime correction only',
            }
        }

    return discount_total, None
