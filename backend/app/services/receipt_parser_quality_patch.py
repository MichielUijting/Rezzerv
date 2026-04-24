from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import receipt_service as _receipt_service

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    raw = str(value).replace('€', '').replace('EUR', '').replace('eur', '').strip()
    if not raw:
        return None
    raw = raw.replace('.', '').replace(',', '.') if ',' in raw and '.' in raw else raw.replace(',', '.')
    cleaned = ''.join(ch for ch in raw if ch.isdigit() or ch in {'-', '.'})
    if cleaned in {'', '-', '.', '-.'}:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _as_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for line in lines or []:
        if line.get('line_total') is None:
            continue
        label = str(line.get('normalized_label') or line.get('raw_label') or '').strip()
        if not label:
            continue
        cleaned = dict(line)
        cleaned['normalized_label'] = label
        cleaned['raw_label'] = str(cleaned.get('raw_label') or label).strip()
        normalized.append(cleaned)
    return normalized


def _line_financials(lines: list[dict[str, Any]], discount_total: Decimal | None) -> tuple[Decimal, Decimal, Decimal]:
    gross_sum = Decimal('0.00')
    line_discount_sum = Decimal('0.00')
    for line in lines:
        gross_sum += _parse_decimal(line.get('line_total')) or Decimal('0.00')
        line_discount_sum += _parse_decimal(line.get('discount_amount')) or Decimal('0.00')
    effective_discount = discount_total if discount_total is not None else line_discount_sum
    if effective_discount is None:
        effective_discount = Decimal('0.00')
    net_sum = (gross_sum + effective_discount).quantize(Decimal('0.01'))
    return gross_sum.quantize(Decimal('0.01')), effective_discount.quantize(Decimal('0.01')), net_sum


def _totals_match(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None) -> bool:
    if total_amount is None or not lines:
        return False
    _, _, net_sum = _line_financials(lines, discount_total)
    try:
        return abs(net_sum - Decimal(total_amount).quantize(Decimal('0.01'))) <= Decimal('0.05')
    except Exception:
        return False


def _zero_discount_case(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None) -> bool:
    if total_amount is None or not lines:
        return False
    try:
        if Decimal(total_amount).quantize(Decimal('0.01')) != Decimal('0.00'):
            return False
    except Exception:
        return False
    gross_sum, _, net_sum = _line_financials(lines, discount_total)
    return gross_sum >= Decimal('0.00') and abs(net_sum) <= Decimal('0.05')


def _reclassify_result(result: Any) -> Any:
    if result is None or not getattr(result, 'is_receipt', False):
        return result

    result.lines = _normalize_receipt_lines(getattr(result, 'lines', None))
    total_amount = getattr(result, 'total_amount', None)
    discount_total = getattr(result, 'discount_total', None)
    if discount_total is not None:
        discount_total = _parse_decimal(discount_total)
        result.discount_total = discount_total

    if not result.lines:
        result.parse_status = 'manual'
        result.confidence_score = min(float(result.confidence_score or 0.36), 0.36)
        return result

    totals_match = _totals_match(total_amount, result.lines, discount_total)
    zero_discount_case = _zero_discount_case(total_amount, result.lines, discount_total)

    if total_amount is not None and totals_match:
        result.parse_status = 'parsed'
        result.confidence_score = max(float(result.confidence_score or 0.0), 0.82)
    elif total_amount is not None and zero_discount_case:
        result.parse_status = 'partial'
        result.confidence_score = max(float(result.confidence_score or 0.0), 0.62)
    else:
        result.parse_status = 'review_needed'
        result.confidence_score = min(float(result.confidence_score or 0.36), 0.48)

    return result


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str):
    return _reclassify_result(_ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type))


_receipt_service.parse_receipt_content = parse_receipt_content
