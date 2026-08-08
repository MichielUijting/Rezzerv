"""Guarded structured PLUS bbox result builder.

Runtime Type: production, guarded.

Purpose:
- convert PLUS-01K-a readiness diagnostics into structured receipt lines;
- only return a result when readiness is exact and financial closure is exact;
- avoid routing reconstructed PLUS bbox rows through the generic text parser;
- keep non-ready PLUS receipts on the existing parser path.

No database writes happen in this module.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.receipt_ingestion.parsing.plus_bbox_activation_readiness import (
    diagnose_plus_bbox_activation_readiness,
)
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult


_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_PLUS_RE = re.compile(r'\bplus\b', re.IGNORECASE)
_AMOUNT_RE = re.compile(r'(?<!\d)[€CE£]?-?\d{1,6}(?:[\.,]\d{2})(?!\d)', re.IGNORECASE)
_QTY_RE = re.compile(r'^\s*[+*]?\s*(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\b\s*(?P<label>.+)$', re.IGNORECASE)


def _normalize(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    cleaned = cleaned.replace('€', '').replace('£', '')
    cleaned = re.sub(r'^[CEe]\s*', '', cleaned)
    cleaned = re.sub(r'\s+', '', cleaned)
    cleaned = cleaned.replace(',', '.')
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float | None:
    amount = _decimal(value)
    return float(amount) if amount is not None else None


def _is_plus_image_context(filename: str | None, runtime_lines: list[str]) -> bool:
    suffix = Path(str(filename or '')).suffix.lower()
    if suffix and suffix not in _IMAGE_EXTENSIONS:
        return False
    haystack = ' '.join([str(filename or '')] + [str(line or '') for line in runtime_lines[:16]])
    return bool(_PLUS_RE.search(haystack))


def _row_text(row: dict[str, Any]) -> str:
    for key in ('reconstructed_line', 'raw_line', 'line'):
        value = _normalize(row.get(key))
        if value:
            return value
    return ''


def _clean_amount_token(token: str) -> str:
    value = str(token or '').strip()
    value = value.replace('€', '').replace('£', '')
    value = re.sub(r'^[CEe]\s*', '', value)
    value = value.replace('.', ',')
    return value


def _parse_structured_article_row(row: dict[str, Any], *, source_index: int, filename: str | None) -> dict[str, Any] | None:
    raw_line = _row_text(row)
    if not raw_line:
        return None

    matches = list(_AMOUNT_RE.finditer(raw_line))
    if not matches:
        return None

    total_token = matches[-1].group(0)
    total_amount = _decimal(total_token)
    if total_amount is None:
        return None

    unit_price = total_amount
    if len(matches) >= 2:
        unit_candidate = _decimal(matches[-2].group(0))
        if unit_candidate is not None:
            unit_price = unit_candidate

    label_part = raw_line[:matches[0].start()].strip(' .:-+*')
    quantity = None

    qty_match = _QTY_RE.match(label_part)
    if qty_match:
        quantity = _float(qty_match.group('qty'))
        label_part = qty_match.group('label').strip(' .:-+*')

    label = _normalize(label_part)
    if not label:
        return None

    return {
        'raw_label': label,
        'normalized_label': label,
        'quantity': quantity,
        'unit': None,
        'unit_price': float(unit_price),
        'line_total': float(total_amount),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.91,
        'source_index': source_index,
        'producer_trace': {
            'source': 'PLUS-01L-c_structured_bbox_result',
            'filename': filename,
            'raw_line': raw_line,
            'financially_guarded': True,
            'parser_path': 'plus_bbox_structured_result',
        },
    }


def _build_structured_lines(diag: dict[str, Any], *, filename: str | None) -> list[dict[str, Any]]:
    structured: list[dict[str, Any]] = []
    source_index = 0

    for row in diag.get('article_rows') or []:
        parsed = _parse_structured_article_row(row, source_index=source_index, filename=filename)
        source_index += 1
        if parsed is not None:
            structured.append(parsed)

    for group_name in ('bbox_non_article_financial_rows', 'extra_runtime_non_article_financial_rows'):
        for row in diag.get(group_name) or []:
            parsed = _parse_structured_article_row(row, source_index=source_index, filename=filename)
            source_index += 1
            if parsed is not None:
                parsed['producer_trace'] = {
                    **(parsed.get('producer_trace') or {}),
                    'non_article_financial_row': True,
                    'non_article_financial_group': group_name,
                }
                structured.append(parsed)

    return structured


def _line_total_sum(lines: list[dict[str, Any]]) -> Decimal:
    total = Decimal('0.00')
    for line in lines:
        value = _decimal(line.get('line_total'))
        if value is not None:
            total += value
        discount = _decimal(line.get('discount_amount'))
        if discount is not None:
            total += discount
    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def build_plus_bbox_structured_result(
    *,
    filename: str | None,
    runtime_lines: list[str],
    texts: list[Any],
    boxes: list[Any],
    confidence_score: float | None = None,
    current_receipt_only: bool = True,
    excludes_deleted: bool = True,
    excludes_archived: bool = True,
) -> ReceiptParseResult | None:
    """Build a guarded structured ReceiptParseResult for ready PLUS image receipts."""

    original_lines = list(runtime_lines or [])

    if not current_receipt_only or not excludes_deleted or not excludes_archived:
        return None

    if not _is_plus_image_context(filename, original_lines):
        return None

    if not texts or not boxes:
        return None

    diag = diagnose_plus_bbox_activation_readiness(texts, boxes, original_lines)
    if not diag.get('ready_for_activation'):
        return None

    financial = diag.get('financial') or {}
    if not financial.get('exact_subtotal_match') or not financial.get('exact_total_match'):
        return None

    total_amount = _decimal(financial.get('total_amount'))
    discount_total = _decimal(financial.get('discount_total')) or Decimal('0.00')
    expected_pre_discount = _decimal(financial.get('pre_discount_total'))
    expected_net = _decimal(financial.get('net_total'))

    if total_amount is None or expected_pre_discount is None or expected_net is None:
        return None

    structured_lines = _build_structured_lines(diag, filename=filename)
    if not structured_lines:
        return None

    line_sum = _line_total_sum(structured_lines)
    if line_sum != expected_pre_discount:
        return None

    if (line_sum + discount_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) != total_amount:
        return None

    return ReceiptParseResult(
        is_receipt=True,
        parse_status='parsed',
        confidence_score=round(float(confidence_score or 0.91), 4),
        store_name='Plus',
        purchase_at=None,
        total_amount=total_amount,
        discount_total=discount_total,
        currency='EUR',
        lines=structured_lines,
        store_branch=None,
        parser_diagnostics={
            'plus_01l_c_structured_bbox_result': {
                'applied': True,
                'version': 'PLUS-01L-c',
                'scope': diag.get('scope') or {
                    'current_receipts_only': True,
                    'excludes_deleted': True,
                    'excludes_archived': True,
                    'no_bulk_backfill_without_explicit_instruction': True,
                },
                'financial': financial,
                'counts': diag.get('counts') or {},
                'line_sum': float(line_sum),
                'discount_total': float(discount_total),
                'net_total': float((line_sum + discount_total).quantize(Decimal('0.01'))),
            }
        },
    )


__all__ = ['build_plus_bbox_structured_result']
