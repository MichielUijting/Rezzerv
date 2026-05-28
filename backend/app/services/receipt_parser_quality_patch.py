from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.receipt_ingestion.profiles.totals_router import resolve_profile_total_amount
from app.services import receipt_service as _receipt_service
from app.services.receipt_line_classifier import (
    LINE_CATEGORY_ITEM,
    LINE_CATEGORY_ITEM_LABEL,
    extract_amount_tokens,
    normalize_ocr_line,
)
from app.services.store_profiles.base import classify_line_for_store

_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines

PRODUCT_LINE_BLACKLIST = (
    'totaal', 'btw', 'betaling', 'betaald', 'pin', 'pinnen', 'bankpas', 'kaart',
    'terminal', 'transactie', 'autorisatie', 'subtotaal', 'wisselgeld',
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


def _is_non_product_label(value: Any, store_name: str | None = None, filename: str | None = None) -> bool:
    label = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not label:
        return True
    category = classify_line_for_store(label, store_name=store_name, filename=filename)
    return category not in {LINE_CATEGORY_ITEM, LINE_CATEGORY_ITEM_LABEL}


def merge_lines(lines: list[str], store_name: str | None = None, filename: str | None = None) -> list[str]:
    merged: list[str] = []
    buffer: str | None = None
    amount_at_end = re.compile(r'-?\d{1,6}[\.,]\d{2}\s*(?:eur)?\s*$', re.IGNORECASE)
    price_only = re.compile(r'^-?\d{1,6}[\.,]\d{2}\s*(?:eur)?$', re.IGNORECASE)

    for raw_line in lines or []:
        text = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if not text:
            continue

        if _is_non_product_label(text, store_name=store_name, filename=filename) and not extract_amount_tokens(text):
            if buffer:
                merged.append(buffer)
                buffer = None
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


def is_product_line(text: str, store_name: str | None = None, filename: str | None = None) -> bool:
    candidate = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(candidate) < 4:
        return False
    if classify_line_for_store(candidate, store_name=store_name, filename=filename) != LINE_CATEGORY_ITEM:
        return False
    if re.fullmatch(r'[-+]?\d+[\.,]\d{2}(?:\s+[-+]?\d+[\.,]\d{2})*', candidate):
        return False
    if any(marker in candidate.lower() for marker in PRODUCT_LINE_BLACKLIST):
        return False
    return True


def _generic_product_line_from_text(text: str, source_index: int, store_name: str | None = None, filename: str | None = None) -> dict[str, Any] | None:
    if not is_product_line(text, store_name=store_name, filename=filename):
        return None

    prices = extract_amount_tokens(text)
    if not prices:
        return None

    unit_price = _parse_decimal(prices[0])
    line_total = _parse_decimal(prices[-1])
    if line_total is None:
        return None

    normalized_text = normalize_ocr_line(text)
    label = normalized_text[: normalized_text.rfind(prices[-1])].strip(' .:-')
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


def _generic_lines_from_merged_text(text_lines: list[str], store_name: str | None = None, filename: str | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, line in enumerate(merge_lines(text_lines, store_name=store_name, filename=filename)):
        parsed = _generic_product_line_from_text(line, index, store_name=store_name, filename=filename)
        if parsed is not None:
            result.append(parsed)
    return _dedupe_lines(result)


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for line in lines or []:
        if line.get('line_total') is None:
            continue
        normalized.append(dict(line))
    return _dedupe_lines(normalized)


def _apply_profile_total_resolution(result: Any, text_lines: list[str], filename: str) -> Any:
    if result is None or not getattr(result, 'is_receipt', False):
        return result

    resolution = resolve_profile_total_amount(text_lines, filename, store_name=getattr(result, 'store_name', None))
    diagnostics = dict(getattr(result, 'parser_diagnostics', None) or {})
    diagnostics.update(resolution.diagnostics)
    result.parser_diagnostics = diagnostics

    # R9-36C: total_amount is profile-only. If no profile total is available,
    # it must remain None. Generic total detection may not mask this.
    result.total_amount = resolution.amount
    return result


def _reclassify_result(result: Any) -> Any:
    if result is None or not getattr(result, 'is_receipt', False):
        return result

    result.lines = _normalize_receipt_lines(getattr(result, 'lines', None))

    if not result.lines:
        result.parse_status = 'manual'
        result.confidence_score = min(float(result.confidence_score or 0.36), 0.36)
        return result

    result.parse_status = 'parsed'
    result.confidence_score = max(float(result.confidence_score or 0.0), 0.82)
    return result


def _parse_result_from_text_lines_with_merge(text_lines: list[str], filename: str, **kwargs: Any):
    merged_lines = merge_lines(text_lines, filename=filename)
    result = _ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(merged_lines, filename, **kwargs)
    result = _apply_profile_total_resolution(result, text_lines, filename)

    if getattr(result, 'is_receipt', False):
        fallback_lines = _generic_lines_from_merged_text(
            merged_lines,
            store_name=getattr(result, 'store_name', None),
            filename=filename,
        )
        if fallback_lines:
            result.lines = fallback_lines

    return _reclassify_result(result)


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str):
    result = _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
    # If this route bypasses _parse_result_from_text_lines, do not keep a hidden
    # generic total. A later profile route/debug reparse may restore it explicitly.
    if result is not None and getattr(result, 'is_receipt', False):
        diagnostics = dict(getattr(result, 'parser_diagnostics', None) or {})
        diagnostics.setdefault('total_resolution', {
            'source': 'none',
            'profile': None,
            'amount': None,
            'explicit_total_found': False,
            'reason': 'profile_total_not_resolved_on_parse_receipt_content_wrapper',
        })
        result.parser_diagnostics = diagnostics
        if diagnostics.get('total_resolution', {}).get('source') != 'profile':
            result.total_amount = None
    return _reclassify_result(result)


def install_parser_quality_patch(*_: Any) -> bool:
    _receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_merge
    _receipt_service.parse_receipt_content = parse_receipt_content
    return True


install_parser_quality_patch()
