from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
import re

from app.receipt_ingestion.amounts import parse_decimal


def _normalize_fingerprint_text(value: Any) -> str:
    normalized = re.sub(r'\s+', ' ', str(value or '').strip().lower())
    normalized = re.sub(r'[^a-z0-9\u20ac.,:;\-_/ ]+', '', normalized)
    return normalized.strip()


def _is_plausible_purchase_at(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return False
    current_year = datetime.utcnow().year
    return current_year - 10 <= parsed.year <= current_year + 1


def _is_plausible_total_amount(value: Decimal | None) -> bool:
    if value is None:
        return False
    try:
        amount = Decimal(value).quantize(Decimal('0.01'))
    except Exception:
        return False
    return Decimal('0.00') <= amount <= Decimal('10000.00')


def _build_receipt_fingerprint(store_name: str | None, purchase_at: str | None, total_amount: Decimal | None, lines: list[dict[str, Any]]) -> str:
    store_part = _normalize_fingerprint_text(store_name)
    purchase_part = ''
    if purchase_at:
        try:
            purchase_part = datetime.fromisoformat(str(purchase_at).replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
        except Exception:
            purchase_part = _normalize_fingerprint_text(purchase_at)
    total_part = f"{Decimal(total_amount).quantize(Decimal('0.01')):.2f}" if total_amount is not None else ''
    line_parts: list[str] = []
    for line in lines[:12]:
        label = _normalize_fingerprint_text(line.get('normalized_label') or line.get('raw_label'))
        if not label:
            continue
        amount = parse_decimal(str(line.get('line_total')))
        amount_part = f"{amount:.2f}" if amount is not None else ''
        line_parts.append(f"{label}|{amount_part}")
    return '||'.join([store_part, purchase_part, total_part, '##'.join(line_parts)])


def build_receipt_fingerprint_from_parse_result(parse_result: Any | None) -> str:
    if not parse_result or not parse_result.is_receipt:
        return ''
    purchase_at = parse_result.purchase_at if _is_plausible_purchase_at(parse_result.purchase_at) else None
    total_amount = parse_result.total_amount if _is_plausible_total_amount(parse_result.total_amount) else None
    return _build_receipt_fingerprint(parse_result.store_name, purchase_at, total_amount, parse_result.lines)
