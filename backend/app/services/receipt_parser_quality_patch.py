from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import receipt_service as _receipt_service

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines

PRODUCT_LINE_BLACKLIST = (
    'totaal',
    'btw',
    'betaling',
    'betaald',
    'pin',
    'pinnen',
    'bankpas',
    'kaart',
    'terminal',
    'transactie',
    'autorisatie',
    'subtotaal',
    'wisselgeld',
)


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


def merge_lines(lines: list[str]) -> list[str]:
    """Merge detached OCR product labels with following price-only lines before parsing."""
    merged: list[str] = []
    buffer: str | None = None
    amount_at_end = re.compile(r'-?\d{1,6}[\.,]\d{2}\s*(?:eur)?\s*$', re.IGNORECASE)
    price_only = re.compile(r'^-?\d{1,6}[\.,]\d{2}\s*(?:eur)?$', re.IGNORECASE)

    for raw_line in lines or []:
        text = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if not text:
            continue

        if amount_at_end.search(text):
            if buffer and price_only.match(text):
                merged.append(f'{buffer} {text}')
                buffer = None
            else:
                if buffer:
                    merged.append(buffer)
                    buffer = None
                merged.append(text)
            continue

        if buffer:
            merged.append(buffer)
        buffer = text

    if buffer:
        merged.append(buffer)
    return merged


def is_product_line(text: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(candidate) < 4:
        return False
    if not re.search(r'-?\d{1,6}[\.,]\d{2}', candidate):
        return False
    lowered = candidate.lower()
    if any(marker in lowered for marker in PRODUCT_LINE_BLACKLIST):
        return False
    if re.fullmatch(r'[-+]?\d+[\.,]\d{2}(?:\s+[-+]?\d+[\.,]\d{2})*', candidate):
        return False
    return True


def _generic_product_line_from_text(text: str, source_index: int) -> dict[str, Any] | None:
    if not is_product_line(text):
        return None
    prices = re.findall(r'-?\d{1,6}[\.,]\d{2}', text)
    if not prices:
        return None
    unit_price = _parse_decimal(prices[0])
    line_total = _parse_decimal(prices[-1])
    if line_total is None:
        return None
    label = text[: text.rfind(prices[-1])].strip(' .:-')
    label = re.sub(r'\b\d+\s*[xX]\s*$', '', label).strip(' .:-')
    if not label or len(label) < 2:
        return None
    quantity = None
    qty_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*[xX]\b', text)
    if qty_match:
        quantity = _as_float(_parse_decimal(qty_match.group(1)))
    return {
        'raw_label': label[:255],
        'normalized_label': label[:255],
        'quantity': quantity,
        'unit': None,
        'unit_price': _as_float(unit_price),
        'line_total': _as_float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.58,
        'source_index': source_index,
    }


def _dedupe_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in lines or []:
        key = (
            re.sub(r'\s+', ' ', str(line.get('normalized_label') or line.get('raw_label') or '')).strip().lower(),
            str(line.get('line_total') or ''),
            str(line.get('source_index') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _generic_lines_from_merged_text(text_lines: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, line in enumerate(merge_lines(text_lines)):
        parsed = _generic_product_line_from_text(line, index)
        if parsed is not None:
            result.append(parsed)
    return _dedupe_lines(result)


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
    return _dedupe_lines(normalized)


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


def _choose_better_lines(existing_lines: list[dict[str, Any]], fallback_lines: list[dict[str, Any]], total_amount: Decimal | None, discount_total: Decimal | None) -> list[dict[str, Any]]:
    if not fallback_lines:
        return existing_lines
    if not existing_lines:
        return fallback_lines
    if _totals_match(total_amount, fallback_lines, discount_total) and not _totals_match(total_amount, existing_lines, discount_total):
        return fallback_lines
    if len(fallback_lines) > len(existing_lines) and len(existing_lines) <= 1:
        return fallback_lines
    return existing_lines


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


def _parse_result_from_text_lines_with_merge(text_lines: list[str], filename: str, **kwargs: Any):
    merged_lines = merge_lines(text_lines)
    result = _ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(merged_lines, filename, **kwargs)
    fallback_lines = _generic_lines_from_merged_text(merged_lines)
    if getattr(result, 'is_receipt', False):
        discount_total = _parse_decimal(getattr(result, 'discount_total', None))
        result.lines = _choose_better_lines(
            _normalize_receipt_lines(getattr(result, 'lines', None)),
            fallback_lines,
            getattr(result, 'total_amount', None),
            discount_total,
        )
    return _reclassify_result(result)


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str):
    return _reclassify_result(_ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type))


_receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_merge
_receipt_service.parse_receipt_content = parse_receipt_content
