from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.services import receipt_service

_ORIGINAL_FILTER = receipt_service._filter_non_product_receipt_lines

SAVINGS_WORDS = ('koopzegel', 'koopzegels', 'spaarzegel', 'spaarzegels', 'pluspunt', 'pluspunten')
BLOCK_WORDS = ('totaal', 'subtotaal', 'btw', 'betaling', 'betaald', 'bankpas', 'pinnen', 'aantal artikelen', 'spaaracties')


def _money(value: Any) -> Decimal | None:
    try:
        raw = str(value or '').replace(',', '.')
        raw = re.sub(r'[^0-9\-.]', '', raw)
        return Decimal(raw).quantize(Decimal('0.01')) if raw else None
    except Exception:
        return None


def _is_priced_savings(line: dict[str, Any]) -> bool:
    label = str(line.get('raw_label') or line.get('normalized_label') or '').strip().lower()
    amount = _money(line.get('line_total'))
    return bool(label and amount is not None and amount > 0 and any(word in label for word in SAVINGS_WORDS) and not any(word in label for word in BLOCK_WORDS))


def _key(line: dict[str, Any]) -> tuple[str, str, str]:
    label = re.sub(r'\s+', ' ', str(line.get('raw_label') or line.get('normalized_label') or '')).strip().lower()
    return (label, str(line.get('line_total') or ''), str(line.get('source_index') or ''))


def _filter_with_savings(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = [line for line in (lines or []) if _is_priced_savings(line)]
    rest = [line for line in (lines or []) if not _is_priced_savings(line)]
    result = list(_ORIGINAL_FILTER(rest))
    seen = {_key(line) for line in result}
    for line in keep:
        key = _key(line)
        if key not in seen:
            result.append(line)
            seen.add(key)
    return sorted(result, key=lambda item: int(item.get('source_index') or 0))


def install_receipt_savings_filter_patch() -> bool:
    if getattr(receipt_service, '_rezzerv_savings_filter_patch_installed', False):
        return False
    receipt_service._filter_non_product_receipt_lines = _filter_with_savings
    receipt_service._rezzerv_savings_filter_patch_installed = True
    return True


install_receipt_savings_filter_patch()
