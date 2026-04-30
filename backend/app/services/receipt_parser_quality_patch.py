from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import receipt_service as _receipt_service

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines

# Conservative parser quality layer.
# Principle: preserve possible article lines first; status remains governed by Baseline V4.
PRODUCT_LINE_BLACKLIST = (
    'totaal', 'btw', 'betaling', 'betaald', 'pin', 'pinnen', 'bankpas', 'kaart',
    'terminal', 'transactie', 'autorisatie', 'subtotaal', 'sub totaal', 'wisselgeld',
)

SAVINGS_LINE_TOKENS = (
    'koopzegel', 'koopzegels', 'spaarzegel', 'spaarzegels', 'e-spaarzegel',
    'e-spaarzegels', 'espaarzegel', 'espaarzegels', 'pluspunt', 'pluspunten',
    'spaarpunt', 'spaarpunten',
)

SAVINGS_LINE_EXCLUDE_TOKENS = (
    'totaal', 'subtotaal', 'sub totaal', 'btw', 'betaling', 'betaald', 'bankpas', 'pin',
    'pinnen', 'aantal artikelen',
)

NEGATIVE_ADJUSTMENT_TOKENS = (
    'korting', 'gratis', 'voordeel', 'coupon', 'actieprijs', 'retour', 'retouremballage',
    'statiegeld retour', 'lidl plus', 'lidlplus',
)

LOYALTY_ONLY_TOKENS = (
    'pluspunten digitaal', 'pluspunten', 'pluspunt', 'messen digitaal', 'zegel', 'zegels',
    'spaarpunt', 'spaarpunten',
)

_AMOUNT_PATTERN = r'-?\d{1,6}[\.,]\d{2}'


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


def _line_label(line: dict[str, Any]) -> str:
    return re.sub(r'\s+', ' ', str(line.get('normalized_label') or line.get('raw_label') or '')).strip()


def _line_text(line: dict[str, Any]) -> str:
    return re.sub(r'\s+', ' ', f"{_line_label(line)} {line.get('line_total') or ''}").strip()


def _compact(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '') if ch.isalnum())


def _is_negative_adjustment_text(text: str) -> bool:
    lowered = re.sub(r'\s+', ' ', str(text or '')).strip().lower()
    if not lowered:
        return False
    amount_values = [_parse_decimal(match) for match in re.findall(_AMOUNT_PATTERN, lowered)]
    return any(value is not None and value < 0 for value in amount_values) and any(token in lowered for token in NEGATIVE_ADJUSTMENT_TOKENS)


def _is_loyalty_only_text(text: str) -> bool:
    lowered = re.sub(r'\s+', ' ', str(text or '')).strip().lower()
    compact = _compact(lowered)
    if not lowered:
        return False
    if 'aantalartikelen' in compact:
        return False
    return any(token in lowered for token in LOYALTY_ONLY_TOKENS) or 'pluspuntendigitaal' in compact


def _is_savings_label_without_amount(text: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not candidate:
        return False
    lowered = candidate.lower()
    if any(marker in lowered for marker in SAVINGS_LINE_EXCLUDE_TOKENS):
        return False
    if not any(token in lowered for token in SAVINGS_LINE_TOKENS):
        return False
    return not bool(re.search(_AMOUNT_PATTERN, candidate))


def _split_compound_product_line(text: str) -> list[str]:
    """Split one OCR/PDF line when it very clearly contains multiple product/price pairs.

    This is deliberately conservative: quantity patterns like "2 x 0,79 1,58" stay together.
    """
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not candidate:
        return []
    if re.search(r'\b\d+(?:[\.,]\d+)?\s*[xX]\s*' + _AMOUNT_PATTERN, candidate):
        return [candidate]
    lowered = candidate.lower()
    if any(marker in lowered for marker in ('totaal', 'subtotaal', 'sub totaal', 'btw', 'betaling', 'bankpas', 'terminal')):
        return [candidate]
    matches = list(re.finditer(_AMOUNT_PATTERN, candidate))
    if len(matches) <= 1:
        return [candidate]
    segments: list[str] = []
    start = 0
    for match in matches:
        segment = candidate[start:match.end()].strip(' .;|')
        if segment and re.search(r'[A-Za-zÀ-ÿ]', segment):
            segments.append(segment)
        start = match.end()
    trailing = candidate[start:].strip(' .;|')
    if trailing and segments:
        segments[-1] = f'{segments[-1]} {trailing}'.strip()
    return segments or [candidate]


def merge_lines(lines: list[str]) -> list[str]:
    """Merge detached OCR/PDF labels with following price-only lines and split clear compound rows."""
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines or []]
    normalized_lines = [line for line in normalized_lines if line]
    merged: list[str] = []
    i = 0
    amount_at_end = re.compile(r'-?\d{1,6}[\.,]\d{2}\s*(?:eur)?\s*$', re.IGNORECASE)
    price_only = re.compile(r'^-?\d{1,6}[\.,]\d{2}\s*(?:eur)?$', re.IGNORECASE)

    while i < len(normalized_lines):
        text = normalized_lines[i]
        next_text = normalized_lines[i + 1] if i + 1 < len(normalized_lines) else ''

        if _is_savings_label_without_amount(text) and price_only.match(next_text):
            merged.extend(_split_compound_product_line(f'{text} {next_text}'))
            i += 2
            continue

        if not amount_at_end.search(text) and price_only.match(next_text):
            lowered = text.lower()
            if not any(marker in lowered for marker in PRODUCT_LINE_BLACKLIST):
                merged.extend(_split_compound_product_line(f'{text} {next_text}'))
                i += 2
                continue

        merged.extend(_split_compound_product_line(text))
        i += 1
    return merged


def _is_savings_or_points_line(text: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(candidate) < 4:
        return False
    lowered = candidate.lower()
    if not any(token in lowered for token in SAVINGS_LINE_TOKENS):
        return False
    if any(marker in lowered for marker in SAVINGS_LINE_EXCLUDE_TOKENS):
        return False
    return bool(re.search(_AMOUNT_PATTERN, candidate))


def is_product_line(text: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(candidate) < 4:
        return False
    if _is_negative_adjustment_text(candidate) or _is_loyalty_only_text(candidate):
        return False
    if not re.search(_AMOUNT_PATTERN, candidate):
        return False
    lowered = candidate.lower()
    if any(marker in lowered for marker in PRODUCT_LINE_BLACKLIST) and not _is_savings_or_points_line(candidate):
        return False
    if re.fullmatch(r'[-+]?\d+[\.,]\d{2}(?:\s+[-+]?\d+[\.,]\d{2})*', candidate):
        return False
    return True


def _generic_product_line_from_text(text: str, source_index: int) -> dict[str, Any] | None:
    if not is_product_line(text):
        return None
    prices = re.findall(_AMOUNT_PATTERN, text)
    if not prices:
        return None
    unit_price = _parse_decimal(prices[0])
    line_total = _parse_decimal(prices[-1])
    if line_total is None:
        return None
    label = text[: text.rfind(prices[-1])].strip(' .:-')
    if not label and _is_savings_or_points_line(text):
        label = text[text.find(prices[0]) + len(prices[0]):].strip(' .:-')
    label = re.sub(r'\b\d+\s*[xX]\s*$', '', label).strip(' .:-')
    leading_savings_qty = None
    if _is_savings_or_points_line(text):
        qty_prefix = re.match(r'^(\d+(?:[\.,]\d+)?)\s+(.+)$', label)
        if qty_prefix:
            leading_savings_qty = _parse_decimal(qty_prefix.group(1))
            label = qty_prefix.group(2).strip(' .:-')
    if not label or len(label) < 2:
        return None
    quantity = None
    qty_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*[xX]\b', text)
    if qty_match:
        quantity = _as_float(_parse_decimal(qty_match.group(1)))
    elif leading_savings_qty is not None:
        quantity = _as_float(leading_savings_qty)
    elif _is_savings_or_points_line(text):
        quantity = 1.0
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


def _line_key(line: dict[str, Any]) -> tuple[str, str]:
    return (_compact(_line_label(line)), str(line.get('line_total') or ''))


def _dedupe_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in lines or []:
        key = (_line_key(line)[0], _line_key(line)[1], str(line.get('source_index') or ''))
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
    excluded_adjustments: list[Decimal] = []
    for line in lines or []:
        if line.get('line_total') is None:
            continue
        label = _line_label(line)
        if not label:
            continue
        text = _line_text(line)
        if _is_negative_adjustment_text(text):
            excluded_adjustments.append(_parse_decimal(line.get('line_total')) or Decimal('0.00'))
            continue
        if _is_loyalty_only_text(text):
            continue
        cleaned = dict(line)
        cleaned['normalized_label'] = label
        cleaned['raw_label'] = str(cleaned.get('raw_label') or label).strip()
        normalized.append(cleaned)

    # Quantity split for exactly counted identical units, e.g. AH foto 3: 2 x 2,70 = 5,40.
    expanded: list[dict[str, Any]] = []
    for line in normalized:
        quantity = _parse_decimal(line.get('quantity'))
        unit_price = _parse_decimal(line.get('unit_price'))
        line_total = _parse_decimal(line.get('line_total'))
        if quantity is not None and unit_price is not None and line_total is not None:
            if quantity == quantity.to_integral_value() and Decimal('2') <= quantity <= Decimal('4') and abs((unit_price * quantity) - line_total) <= Decimal('0.03'):
                for copy_index in range(int(quantity)):
                    item = dict(line)
                    item['quantity'] = 1.0
                    item['unit_price'] = float(unit_price)
                    item['line_total'] = float(unit_price)
                    item['source_index'] = f"{line.get('source_index')}.{copy_index + 1}"
                    expanded.append(item)
                continue
        expanded.append(line)

    return _dedupe_lines(expanded)


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


def _contains_savings_line(lines: list[dict[str, Any]]) -> bool:
    return any(_is_savings_or_points_line(f"{line.get('raw_label') or line.get('normalized_label') or ''} {line.get('line_total') or ''}") for line in lines or [])


def _merge_missing_savings_lines(existing_lines: list[dict[str, Any]], fallback_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing_lines or [])
    existing_keys = {_line_key(line) for line in merged}
    for line in fallback_lines or []:
        if not _is_savings_or_points_line(f"{line.get('raw_label') or line.get('normalized_label') or ''} {line.get('line_total') or ''}"):
            continue
        key = _line_key(line)
        if key in existing_keys:
            continue
        merged.append(line)
        existing_keys.add(key)
    return _dedupe_lines(merged)


def _choose_better_lines(existing_lines: list[dict[str, Any]], fallback_lines: list[dict[str, Any]], total_amount: Decimal | None, discount_total: Decimal | None) -> list[dict[str, Any]]:
    if not fallback_lines:
        return existing_lines
    if not existing_lines:
        return fallback_lines
    merged_with_savings = _merge_missing_savings_lines(existing_lines, fallback_lines)
    if len(merged_with_savings) > len(existing_lines):
        return merged_with_savings
    if _contains_savings_line(fallback_lines) and not _contains_savings_line(existing_lines) and len(fallback_lines) >= len(existing_lines):
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


def install_parser_quality_patch(main_module: Any | None = None) -> bool:
    if getattr(_receipt_service, '_rezzerv_parser_quality_patch_installed', False):
        if main_module is not None:
            main_module.parse_receipt_content = _receipt_service.parse_receipt_content
        return False
    _receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_merge
    _receipt_service.parse_receipt_content = parse_receipt_content
    _receipt_service._rezzerv_parser_quality_patch_installed = True
    if main_module is not None:
        main_module.parse_receipt_content = parse_receipt_content
    return True


install_parser_quality_patch()
