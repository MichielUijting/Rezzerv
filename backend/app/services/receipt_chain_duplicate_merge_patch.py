from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import receipt_service as _receipt_service

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines


def _normalize_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip()).lower()


def _normalize_label(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', _normalize_text(value))


def _amount(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    raw = str(value).replace('€', '').replace('EUR', '').replace('eur', '').strip()
    raw = raw.replace('.', '').replace(',', '.') if ',' in raw and '.' in raw else raw.replace(',', '.')
    cleaned = ''.join(ch for ch in raw if ch.isdigit() or ch in {'-', '.'})
    if cleaned in {'', '-', '.', '-.'}:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _same_amount(left: Any, right: Any) -> bool:
    left_amount = _amount(left)
    right_amount = _amount(right)
    if left_amount is None or right_amount is None:
        return False
    return abs(left_amount - right_amount) <= Decimal('0.01')


def _line_label(line: dict[str, Any]) -> str:
    return str(line.get('normalized_label') or line.get('raw_label') or '').strip()


def _line_total(line: dict[str, Any]) -> Any:
    return line.get('line_total')


def _store_chain(store_name: Any, filename: str = '') -> str:
    haystack = _normalize_text(f'{store_name or ""} {filename or ""}')
    if 'aldi' in haystack:
        return 'aldi'
    if 'lidl' in haystack:
        return 'lidl'
    return ''


def _is_weight_or_unit_price_companion(line: dict[str, Any]) -> bool:
    label = _normalize_text(_line_label(line))
    compact = _normalize_label(label)
    if not label:
        return False
    if re.search(r'\b\d+[\.,]\d+\s*kg\b', label):
        return True
    if 'kg' in compact and re.search(r'\d', label):
        return True
    if re.search(r'\b\d+[\.,]\d{2}\s*/\s*kg\b', label):
        return True
    if re.fullmatch(r'[0-9,.x ×*/kg]+', label):
        return True
    return False


def _merge_aldi_adjacent_duplicate_products(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        current = dict(lines[index])
        current_label = _normalize_label(_line_label(current))
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line is not None:
            next_label = _normalize_label(_line_label(next_line))
            if current_label and current_label == next_label and _same_amount(_line_total(current), _line_total(next_line)):
                quantity = current.get('quantity')
                try:
                    current['quantity'] = float(quantity or 1) + 1
                except Exception:
                    current['quantity'] = 2
                current['confidence_score'] = max(float(current.get('confidence_score') or 0), 0.72)
                current['duplicate_merge_applied'] = 'aldi_adjacent_same_label_same_amount'
                merged.append(current)
                index += 2
                continue
        merged.append(current)
        index += 1
    return merged


def _merge_lidl_weight_companion_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        current = dict(lines[index])
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line is not None and _same_amount(_line_total(current), _line_total(next_line)):
            current_is_weight = _is_weight_or_unit_price_companion(current)
            next_is_weight = _is_weight_or_unit_price_companion(next_line)
            if current_is_weight != next_is_weight:
                product_line = dict(next_line if current_is_weight else current)
                companion_line = current if current_is_weight else next_line
                product_line['confidence_score'] = max(float(product_line.get('confidence_score') or 0), 0.72)
                product_line['duplicate_merge_applied'] = 'lidl_weight_companion_same_amount'
                product_line['merged_companion_label'] = _line_label(companion_line)
                merged.append(product_line)
                index += 2
                continue
        merged.append(current)
        index += 1
    return merged


def _apply_chain_specific_duplicate_merge(result: Any, filename: str = '') -> Any:
    if result is None or not getattr(result, 'is_receipt', False):
        return result
    lines = list(getattr(result, 'lines', None) or [])
    if not lines:
        return result
    chain = _store_chain(getattr(result, 'store_name', None), filename)
    if chain == 'aldi':
        result.lines = _merge_aldi_adjacent_duplicate_products(lines)
    elif chain == 'lidl':
        result.lines = _merge_lidl_weight_companion_lines(lines)
    return result


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str):
    return _apply_chain_specific_duplicate_merge(_ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type), filename)


def _parse_result_from_text_lines_with_chain_duplicate_merge(text_lines: list[str], filename: str, **kwargs: Any):
    return _apply_chain_specific_duplicate_merge(_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(text_lines, filename, **kwargs), filename)


def install_receipt_chain_duplicate_merge_patch(*_: Any) -> bool:
    _receipt_service.parse_receipt_content = parse_receipt_content
    _receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_chain_duplicate_merge
    return True


install_receipt_chain_duplicate_merge_patch()
