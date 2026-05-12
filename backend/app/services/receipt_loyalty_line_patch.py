from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.services import receipt_parser_quality_patch as qpatch
from app.services.store_profiles.base import should_include_loyalty_line_for_store

_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = qpatch._ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES

LOYALTY_LINE_RE = re.compile(
    r'(?P<label>.*?koop\s*zegels?.*?)\s+(?P<amount>\d{1,6}[\.,]\d{2})\s*$',
    re.IGNORECASE,
)


def _clean_label(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _parse_positive_amount(value: Any) -> Decimal | None:
    amount = qpatch._parse_decimal(value)
    if amount is None or amount <= Decimal('0.00'):
        return None
    return amount


def _is_jumbo_koopzegel_line(value: Any, store_name: Any = None, filename: Any = None) -> bool:
    text = _clean_label(value)
    if not text:
        return False
    if not should_include_loyalty_line_for_store(text, store_name=str(store_name or ''), filename=str(filename or '')):
        return False
    match = LOYALTY_LINE_RE.search(text)
    if not match:
        return False
    return _parse_positive_amount(match.group('amount')) is not None


def _build_jumbo_koopzegel_line(value: Any, source_index: int, store_name: Any = None, filename: Any = None) -> dict[str, Any] | None:
    text = _clean_label(value)
    if not _is_jumbo_koopzegel_line(text, store_name=store_name, filename=filename):
        return None
    match = LOYALTY_LINE_RE.search(text)
    if not match:
        return None
    amount = _parse_positive_amount(match.group('amount'))
    if amount is None:
        return None
    label = _clean_label(match.group('label')).strip(' .:-')
    if not label:
        label = 'Koopzegel'
    return {
        'raw_label': label[:255],
        'normalized_label': label[:255],
        'quantity': 1.0,
        'unit': None,
        'unit_price': qpatch._as_float(amount),
        'line_total': qpatch._as_float(amount),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.86,
        'source_index': source_index,
        'is_loyalty_line': True,
    }


def _signature(line: dict[str, Any]) -> tuple[str, str]:
    label = re.sub(r'\s+', ' ', str(line.get('normalized_label') or line.get('raw_label') or '').strip().lower())
    amount = qpatch._parse_decimal(line.get('line_total'))
    return label, f'{amount:.2f}' if amount is not None else ''


def _append_missing_jumbo_koopzegel_lines(lines: list[dict[str, Any]] | None, text_lines: list[str], store_name: Any = None, filename: Any = None) -> list[dict[str, Any]]:
    result = qpatch._normalize_receipt_lines(lines or [])
    seen = {_signature(line) for line in result}
    for index, text in enumerate(text_lines or []):
        candidate = _build_jumbo_koopzegel_line(text, index, store_name=store_name, filename=filename)
        if candidate is None:
            continue
        sig = _signature(candidate)
        if sig in seen:
            continue
        result.append(candidate)
        seen.add(sig)
    return qpatch._dedupe_lines(result)


def _parse_result_from_text_lines_with_loyalty(text_lines: list[str], filename: str, **kwargs: Any):
    result = _ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(text_lines, filename, **kwargs)
    if not getattr(result, 'is_receipt', False):
        return qpatch._reclassify_result(result)
    store_name = getattr(result, 'store_name', None)
    result.lines = _append_missing_jumbo_koopzegel_lines(
        getattr(result, 'lines', None),
        text_lines,
        store_name=store_name,
        filename=filename,
    )
    return qpatch._reclassify_result(result)


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    # Single-purpose Release A patch: append only explicit Jumbo koopzegel lines.
    # No monkeypatching of qpatch helper functions, so no signature conflicts and no recursion.
    qpatch._parse_result_from_text_lines_with_merge = _parse_result_from_text_lines_with_loyalty
    qpatch._receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_loyalty
    qpatch._receipt_service.parse_receipt_content = qpatch.parse_receipt_content
    return True


install_receipt_loyalty_line_patch()
