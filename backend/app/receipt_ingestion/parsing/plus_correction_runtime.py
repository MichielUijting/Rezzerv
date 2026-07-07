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

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# R9-38C1a:
# Backwards-compatible wrapper. PLUS-specific runtime correction logic has moved
# to app.receipt_ingestion.profiles.plus.corrections.
# Remove this wrapper after receipt_service.py imports the PLUS profile directly.

from app.receipt_ingestion.profiles.plus.corrections import apply_plus_runtime_corrections as _base_apply_plus_runtime_corrections


def _money(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')


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


def apply_plus_runtime_corrections(**kwargs: Any):
    lines, discount_total, diagnostics = _base_apply_plus_runtime_corrections(**kwargs)
    sanitized_lines, removed = _sanitize_implausible_plus_line_discounts(lines)
    if removed:
        diagnostics = dict(diagnostics or {})
        plus_diag = dict(diagnostics.get('r9_38c3a_plus_subtotal_correction_recovery') or {})
        plus_diag['implausible_line_discount_guardrail_applied'] = True
        plus_diag['removed_implausible_line_discounts'] = removed
        diagnostics['r9_38c3a_plus_subtotal_correction_recovery'] = plus_diag
    return sanitized_lines, discount_total, diagnostics


__all__ = ["apply_plus_runtime_corrections"]
