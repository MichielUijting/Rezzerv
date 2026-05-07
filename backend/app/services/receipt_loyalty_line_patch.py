from __future__ import annotations

import re
from typing import Any

from app.services import receipt_parser_quality_patch as qpatch

GENERIC_LOYALTY_PATTERNS = (
    'koopzegel',
    'koopzegels',
    'zegel',
    'zegels',
    'spaar',
    'spaarpunten',
    'punten',
)

STORE_LOYALTY_PATTERNS = {
    'ah': ('koopzegels premium',),
    'albert heijn': ('koopzegels premium',),
    'jumbo': ('koopzegel digitaal',),
    'plus': ('pluspunten',),
}

LOYALTY_EXCLUSION_PATTERNS = (
    'totaal',
    'subtotaal',
    'korting',
    'voordeel',
    'betaling',
    'betaald',
)


def _store_key(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _has_amount(value: Any) -> bool:
    return bool(re.search(r'-?\d{1,6}[\.,]\d{2}', str(value or '')))


def is_loyalty_line_text(value: Any, store_name: Any = None) -> bool:
    text = qpatch._clean_label(value)
    if not text or not _has_amount(text):
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in LOYALTY_EXCLUSION_PATTERNS):
        return False
    store_patterns = STORE_LOYALTY_PATTERNS.get(_store_key(store_name), ())
    if any(pattern in lowered for pattern in store_patterns):
        return True
    return any(pattern in lowered for pattern in GENERIC_LOYALTY_PATTERNS)


def _is_non_product_label(value: Any, store_name: Any = None) -> bool:
    label = qpatch._clean_label(value)
    if not label:
        return True
    if is_loyalty_line_text(label, store_name):
        return False
    if any(pattern.search(label) for pattern in qpatch.NON_PRODUCT_LABEL_PATTERNS):
        return True
    lowered = label.lower()
    return any(marker in lowered for marker in qpatch.PRODUCT_LINE_BLACKLIST if marker not in {'bonus', 'korting', 'voordeel'})


def is_product_line(text: str, store_name: Any = None) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(candidate) < 4 or not _has_amount(candidate):
        return False
    lowered = candidate.lower()
    is_loyalty = is_loyalty_line_text(candidate, store_name)
    if any(marker in lowered for marker in qpatch.PRODUCT_LINE_BLACKLIST) and not is_loyalty:
        return False
    if re.fullmatch(r'[-+]?\d+[\.,]\d{2}(?:\s+[-+]?\d+[\.,]\d{2})*', candidate):
        return False
    return True


def _generic_product_line_from_text(text: str, source_index: int, store_name: Any = None) -> dict[str, Any] | None:
    if not is_product_line(text, store_name):
        return None
    prices = re.findall(r'-?\d{1,6}[\.,]\d{2}', text)
    if not prices:
        return None
    unit_price = qpatch._parse_decimal(prices[0])
    line_total = qpatch._parse_decimal(prices[-1])
    if line_total is None:
        return None
    label = text[: text.rfind(prices[-1])].strip(' .:-')
    label = re.sub(r'\b\d+\s*[xX]\s*$', '', label).strip(' .:-')
    if not label or len(label) < 2 or _is_non_product_label(label, store_name):
        return None
    qty = None
    qty_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*[xX]\b', text)
    if qty_match:
        qty = qpatch._as_float(qpatch._parse_decimal(qty_match.group(1)))
    loyalty = is_loyalty_line_text(text, store_name)
    return {
        'raw_label': label[:255],
        'normalized_label': label[:255],
        'quantity': qty,
        'unit': None,
        'unit_price': qpatch._as_float(unit_price),
        'line_total': qpatch._as_float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.72 if loyalty else 0.58,
        'source_index': source_index,
        'is_loyalty_line': loyalty,
    }


def _generic_lines_from_merged_text(text_lines: list[str], store_name: Any = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, line in enumerate(qpatch.merge_lines(text_lines)):
        parsed = _generic_product_line_from_text(line, index, store_name)
        if parsed is not None:
            result.append(parsed)
    return qpatch._dedupe_lines(result)


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None, store_name: Any = None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for line in lines or []:
        if line.get('line_total') is None:
            continue
        label = str(line.get('normalized_label') or line.get('raw_label') or '').strip()
        if not label or _is_non_product_label(label, store_name):
            continue
        cleaned = dict(line)
        cleaned['normalized_label'] = label
        cleaned['raw_label'] = str(cleaned.get('raw_label') or label).strip()
        if is_loyalty_line_text(label, store_name):
            cleaned['is_loyalty_line'] = True
        normalized.append(cleaned)
    return qpatch._dedupe_lines(normalized)


def _reclassify_result(result: Any) -> Any:
    if result is None or not getattr(result, 'is_receipt', False):
        return result
    result.lines = _normalize_receipt_lines(getattr(result, 'lines', None), getattr(result, 'store_name', None))
    total_amount = getattr(result, 'total_amount', None)
    discount_total = getattr(result, 'discount_total', None)
    if discount_total is not None:
        discount_total = qpatch._parse_decimal(discount_total)
        result.discount_total = discount_total
    if not result.lines:
        result.parse_status = 'manual'
        result.confidence_score = min(float(result.confidence_score or 0.36), 0.36)
        return result
    totals_match = qpatch._totals_match(total_amount, result.lines, discount_total)
    zero_discount_case = qpatch._zero_discount_case(total_amount, result.lines, discount_total)
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
    merged_lines = qpatch.merge_lines(text_lines)
    result = qpatch._ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(merged_lines, filename, **kwargs)
    store_name = getattr(result, 'store_name', None)
    fallback_lines = _generic_lines_from_merged_text(merged_lines, store_name)
    if getattr(result, 'is_receipt', False):
        discount_total = qpatch._parse_decimal(getattr(result, 'discount_total', None))
        result.lines = qpatch._choose_better_lines(
            _normalize_receipt_lines(getattr(result, 'lines', None), store_name),
            fallback_lines,
            getattr(result, 'total_amount', None),
            discount_total,
        )
    return _reclassify_result(result)


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    qpatch._is_non_product_label = _is_non_product_label
    qpatch.is_product_line = is_product_line
    qpatch._generic_product_line_from_text = _generic_product_line_from_text
    qpatch._generic_lines_from_merged_text = _generic_lines_from_merged_text
    qpatch._normalize_receipt_lines = _normalize_receipt_lines
    qpatch._reclassify_result = _reclassify_result
    qpatch._parse_result_from_text_lines_with_merge = _parse_result_from_text_lines_with_merge
    qpatch._receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_merge
    qpatch._receipt_service.parse_receipt_content = qpatch.parse_receipt_content
    return True


install_receipt_loyalty_line_patch()
