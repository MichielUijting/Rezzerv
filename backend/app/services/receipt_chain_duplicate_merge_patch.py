from __future__ import annotations

import re
import sys
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from app.services import receipt_service as _receipt_service

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines
_PATCH_MARKER = '__rezzerv_chain_duplicate_merge_patch_v2__'


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


def _similar_label(left: Any, right: Any, *, threshold: float = 0.92) -> bool:
    left_norm = _normalize_label(left)
    right_norm = _normalize_label(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if abs(len(left_norm) - len(right_norm)) > 1:
        return False
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= threshold


def _merge_adjacent_duplicate_products(
    lines: list[dict[str, Any]],
    *,
    marker: str,
    allow_near_match: bool = False,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        current = dict(lines[index])
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line is not None and _same_amount(_line_total(current), _line_total(next_line)):
            current_label = _line_label(current)
            next_label = _line_label(next_line)
            labels_match = _similar_label(current_label, next_label) if allow_near_match else (_normalize_label(current_label) == _normalize_label(next_label))
            if labels_match:
                try:
                    current['quantity'] = float(current.get('quantity') or 1) + 1
                except Exception:
                    current['quantity'] = 2
                current['confidence_score'] = max(float(current.get('confidence_score') or 0), 0.72)
                current['duplicate_merge_applied'] = marker
                current['merged_companion_label'] = next_label
                merged.append(current)
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
        result.lines = _merge_adjacent_duplicate_products(
            lines,
            marker='aldi_adjacent_near_duplicate_same_amount',
            allow_near_match=True,
        )
    elif chain == 'lidl':
        result.lines = _merge_adjacent_duplicate_products(
            lines,
            marker='lidl_adjacent_duplicate_same_amount',
            allow_near_match=False,
        )
    return result


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str):
    return _apply_chain_specific_duplicate_merge(_ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type), filename)


def _parse_result_from_text_lines_with_chain_duplicate_merge(text_lines: list[str], filename: str, **kwargs: Any):
    return _apply_chain_specific_duplicate_merge(_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(text_lines, filename, **kwargs), filename)


def install_receipt_chain_duplicate_merge_patch(module: Any = None) -> bool:
    if getattr(_receipt_service.parse_receipt_content, _PATCH_MARKER, False):
        return True

    setattr(parse_receipt_content, _PATCH_MARKER, True)
    setattr(_parse_result_from_text_lines_with_chain_duplicate_merge, _PATCH_MARKER, True)
    _receipt_service.parse_receipt_content = parse_receipt_content
    _receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_chain_duplicate_merge

    target_module = module or sys.modules.get('app.main')
    if target_module is not None:
        # app.main imports parse_receipt_content directly, so update that binding too.
        try:
            target_module.parse_receipt_content = parse_receipt_content
        except Exception:
            pass
    return True


install_receipt_chain_duplicate_merge_patch()
