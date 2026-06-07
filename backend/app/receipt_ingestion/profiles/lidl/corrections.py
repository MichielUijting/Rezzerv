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
import re

def _parse_decimal(token: str | None) -> Decimal | None:
    if token is None:
        return None
    try:
        value = str(token).strip().replace("−", "-").replace(",", ".")
        value = re.sub(r"[^0-9.\-]", "", value)
        if value in {"", "-", ".", "-."}:
            return None
        return Decimal(value).quantize(Decimal("0.01"))
    except Exception:
        return None

def _is_lidl_store_context(store_name: str | None, text_lines: list[str] | None = None) -> bool:
    haystack = ' '.join([str(store_name or ''), *(str(line or '') for line in (text_lines or [])[:30])]).lower()
    return 'lidl' in haystack

def _lidl_plus_discount_amounts(text_lines: list[str]) -> list[Decimal]:
    """Extract visible Lidl Plus korting rows as negative amounts."""
    amounts: list[Decimal] = []
    amount_re = re.compile(r'[-−]?\s*\d{1,5}[\.,]\d{2}')
    for raw_line in text_lines or []:
        line = str(raw_line or '').strip()
        lowered = line.lower()
        if 'lidl' not in lowered or 'plus' not in lowered or 'korting' not in lowered:
            continue
        matches = amount_re.findall(line)
        if not matches:
            continue
        # Use the last amount on the discount row. OCR may include noise before it.
        amount = _parse_decimal(matches[-1].replace('−', '-').replace(' ', ''))
        if amount is None:
            continue
        if amount > Decimal('0.00'):
            amount = -amount
        amounts.append(amount.quantize(Decimal('0.01')))
    return amounts

def _lidl_apply_plus_discount_total_to_lines(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
) -> tuple[list[dict[str, Any]], Decimal | None, dict[str, Any] | None]:
    """Normalize Lidl Plus discounts.

    Lidl app receipts print "Lidl Plus korting" directly below the article.
    In parsed output, equal article lines may be merged. Therefore the reliable
    SSOT within the receipt is the sum of visible Lidl Plus discount rows.

    Generic guarded behavior:
    - only Lidl context;
    - only visible "Lidl Plus korting" rows;
    - no filename, receipt-id or article-name matching;
    - when line-level Lidl discount exists, align the total line discount with
      visible Lidl discount total;
    - remove the same amount from receipt-level discount_total to avoid double
      counting.
    """
    if not _is_lidl_store_context(store_name, text_lines):
        return lines, discount_total, None

    visible_discounts = _lidl_plus_discount_amounts(text_lines)
    if not visible_discounts:
        return lines, discount_total, None

    visible_total = sum(visible_discounts, Decimal('0.00')).quantize(Decimal('0.01'))
    if visible_total == Decimal('0.00'):
        return lines, discount_total, None

    adjusted = [dict(line) for line in (lines or [])]

    discount_line_indices = [
        idx for idx, line in enumerate(adjusted)
        if isinstance(line, dict)
        and Decimal(str(line.get('discount_amount') or 0)).quantize(Decimal('0.01')) != Decimal('0.00')
    ]

    # Conservative target:
    # If discounts already exist on Lidl article lines, put the visible total on
    # the first discounted line. This covers merged repeated items such as
    # 2 x "Jonge bladsla" with two visible -0,40 discounts.
    if discount_line_indices:
        target_idx = discount_line_indices[0]
    else:
        # Fallback: attach to the first article line. This matches Lidl layout:
        # a Lidl Plus korting line directly follows the discounted article.
        target_idx = 0 if adjusted else None

    if target_idx is None:
        return lines, discount_total, None

    for idx in discount_line_indices:
        adjusted[idx]['discount_amount'] = None

    adjusted[target_idx]['discount_amount'] = float(visible_total)

    receipt_discount = Decimal(str(discount_total or 0)).quantize(Decimal('0.01'))
    remaining_receipt_discount = receipt_discount

    # If receipt-level discount equals the visible Lidl Plus total, remove it.
    # If it contains more, remove only the visible linked amount and keep rest.
    if receipt_discount != Decimal('0.00'):
        if abs(receipt_discount - visible_total) <= Decimal('0.01'):
            remaining_receipt_discount = Decimal('0.00')
        else:
            remaining_receipt_discount = (receipt_discount - visible_total).quantize(Decimal('0.01'))

    diagnostics = {
        'r9_38d4_lidl_plus_discount_normalization': {
            'applied': True,
            'visible_lidl_plus_discount_total': float(visible_total),
            'visible_lidl_plus_discount_count': len(visible_discounts),
            'target_line_index': int(target_idx),
            'receipt_discount_before': float(receipt_discount),
            'receipt_discount_after': float(remaining_receipt_discount),
            'double_counting_prevented': True,
            'scope': 'Lidl profile runtime correction only',
        }
    }

    return adjusted, (remaining_receipt_discount if remaining_receipt_discount != Decimal('0.00') else None), diagnostics
