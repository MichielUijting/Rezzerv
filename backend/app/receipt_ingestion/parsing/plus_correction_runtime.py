"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# R9-38C1a:
# Backwards-compatible wrapper. PLUS-specific runtime correction logic has moved
# to app.receipt_ingestion.profiles.plus.corrections.
# Remove this wrapper after receipt_service.py imports the PLUS profile directly.

from app.receipt_ingestion.profiles.plus.corrections import apply_plus_runtime_corrections as _base_apply_plus_runtime_corrections

_SUMMARY_AMOUNT_RE = re.compile(r'[€£CE]?-?\d{1,6}(?:[\.,]\d{2})', re.IGNORECASE)


def _money(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')


def _parse_summary_amount_token(value: str) -> Decimal | None:
    raw = str(value or '').upper().replace('€', '').replace('£', '').strip()
    raw = raw.replace('C', '').replace('E', '').replace(',', '.')
    try:
        return Decimal(raw).copy_abs().quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _summary_discount_amounts(text_lines: list[str] | None) -> set[Decimal]:
    amounts: set[Decimal] = set()
    for raw_line in text_lines or []:
        compact = re.sub(r'[^a-z0-9]+', '', str(raw_line or '').lower())
        if 'totalekortingis' not in compact and 'detotalekortingis' not in compact:
            continue
        for token in _SUMMARY_AMOUNT_RE.findall(str(raw_line or '')):
            parsed = _parse_summary_amount_token(token)
            if parsed is not None and parsed > Decimal('0.00'):
                amounts.add(parsed)
    return amounts


def _sanitize_implausible_plus_line_discounts(lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sanitized: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for line in lines:
        adjusted = dict(line)
        line_total = abs(_money(adjusted.get('line_total')))
        discount = _money(adjusted.get('discount_amount'))
        if discount < Decimal('0.00') and line_total > Decimal('0.00') and abs(discount) > line_total + Decimal('0.02'):
            removed.append({
                'target_label': adjusted.get('raw_label') or adjusted.get('normalized_label'),
                'line_total': float(line_total),
                'removed_discount_amount': float(discount),
                'reason': 'discount_exceeds_line_total',
            })
            adjusted['discount_amount'] = None
            trace = dict(adjusted.get('producer_trace') or {})
            trace['plus_implausible_discount_removed'] = {
                'applied': True,
                'line_total': float(line_total),
                'removed_discount_amount': float(discount),
                'reason': 'discount_exceeds_line_total',
                'source': 'PLUS_runtime_guardrail',
            }
            adjusted['producer_trace'] = trace
        sanitized.append(adjusted)
    return sanitized, removed


def _sanitize_summary_plus_line_discounts(lines: list[dict[str, Any]], summary_amounts: set[Decimal]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not summary_amounts:
        return lines, []
    sanitized: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for line in lines:
        adjusted = dict(line)
        discount = _money(adjusted.get('discount_amount'))
        if discount < Decimal('0.00') and abs(discount) in summary_amounts:
            removed.append({
                'target_label': adjusted.get('raw_label') or adjusted.get('normalized_label'),
                'removed_discount_amount': float(discount),
                'reason': 'discount_equals_summary_discount_total',
            })
            adjusted['discount_amount'] = None
            trace = dict(adjusted.get('producer_trace') or {})
            trace['plus_summary_discount_removed'] = {
                'applied': True,
                'removed_discount_amount': float(discount),
                'reason': 'discount_equals_summary_discount_total',
                'source': 'PLUS_summary_discount_guardrail',
            }
            adjusted['producer_trace'] = trace
        sanitized.append(adjusted)
    return sanitized, removed


def apply_plus_runtime_corrections(**kwargs: Any):
    lines, discount_total, diagnostics = _base_apply_plus_runtime_corrections(**kwargs)
    sanitized_lines, removed_implausible = _sanitize_implausible_plus_line_discounts(lines)

    parked_receipt_discount = Decimal('0.00')
    for item in removed_implausible:
        parked_receipt_discount += _money(item.get('removed_discount_amount'))

    if parked_receipt_discount != Decimal('0.00'):
        discount_total = (_money(discount_total) + parked_receipt_discount).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )

    summary_amounts = _summary_discount_amounts(kwargs.get('text_lines'))
    sanitized_lines, removed_summary = _sanitize_summary_plus_line_discounts(sanitized_lines, summary_amounts)
    if removed_implausible or removed_summary:
        diagnostics = dict(diagnostics or {})
        plus_diag = dict(diagnostics.get('r9_38c3a_plus_subtotal_correction_recovery') or {})
        if removed_implausible:
            plus_diag['implausible_line_discount_guardrail_applied'] = True
            plus_diag['removed_implausible_line_discounts'] = removed_implausible
            plus_diag['implausible_line_discounts_parked_as_receipt_discount'] = float(parked_receipt_discount)
        if removed_summary:
            plus_diag['summary_line_discount_guardrail_applied'] = True
            plus_diag['removed_summary_line_discounts'] = removed_summary
        diagnostics['r9_38c3a_plus_subtotal_correction_recovery'] = plus_diag
    return sanitized_lines, discount_total, diagnostics


__all__ = ["apply_plus_runtime_corrections"]
