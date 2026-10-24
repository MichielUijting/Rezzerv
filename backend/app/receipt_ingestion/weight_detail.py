"""Weight continuation evidence at source normalization / explicit legacy repair.

Never used to infer household identity or downstream business permissions.
"""
import re
from decimal import Decimal, InvalidOperation

_DETAIL = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\s*[x×*]\s*(?:€\s*)?(\d+(?:[.,]\d{2,4})?)(?:\s*(?:EUR|€)(?:\s*/\s*(?:kg|g))?)?\s*$', re.I)


def decimal(value):
    try:
        result = Decimal(str(value).replace(',', '.'))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_weight_detail(raw):
    match = _DETAIL.fullmatch(str(raw or ''))
    if not match:
        return None
    qty, unit, price = match.groups()
    qty, price = decimal(qty), decimal(price)
    if qty is None or price is None or qty <= 0 or price <= 0:
        return None
    return qty, unit.lower(), price


def confirmed_weight_continuation(previous, current):
    """Require adjacent source facts, exact SKU and agreement with the paid line."""
    facts = parse_weight_detail(current.get('raw_label'))
    if not facts or parse_weight_detail(previous.get('raw_label')):
        return False
    sku = str(current.get('external_article_code') or '').strip()
    if not sku or sku != str(previous.get('external_article_code') or '').strip():
        return False
    qty, unit, price = facts
    # Do not merge conflicting units / structured quantities or prices.
    if decimal(previous.get('quantity')) != qty or decimal(current.get('quantity')) != qty:
        return False
    if decimal(previous.get('unit_price')) != price or decimal(current.get('unit_price')) != price:
        return False
    total, detail_total = decimal(previous.get('line_total')), decimal(current.get('line_total'))
    if total is None or abs(total - qty * price) > Decimal('0.011'):
        return False
    return detail_total is None or detail_total == 0 or abs(detail_total-total) <= Decimal('0.01')


def normalize_legacy_weight_details(lines):
    """Producer-only fallback for PDF/OCR/HTML parser output, before Canonical V1.

    Keep uncertain observations for review, never publish them as products.
    """
    result, unresolved = [], False
    for original in lines:
        item = dict(original)
        if parse_weight_detail(item.get('raw_label')):
            if result and confirmed_weight_continuation(result[-1], item):
                continue
            item['line_type'] = 'unknown'
            unresolved = True
        result.append(item)
    return result, unresolved
