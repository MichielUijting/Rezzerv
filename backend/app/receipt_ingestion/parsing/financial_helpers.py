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

from decimal import Decimal
from typing import Any, Callable

ParseDecimal = Callable[[str | None], Decimal | None]


def _receipt_line_financials(
    lines: list[dict[str, Any]],
    discount_total: Decimal | None = None,
    *,
    parse_decimal: ParseDecimal,
) -> tuple[Decimal, Decimal, Decimal]:
    gross_sum = Decimal('0.00')
    line_discount_sum = Decimal('0.00')
    for line in lines or []:
        gross_sum += parse_decimal(str(line.get('line_total'))) or Decimal('0.00')
        line_discount_sum += parse_decimal(str(line.get('discount_amount'))) or Decimal('0.00')
    effective_discount = discount_total if discount_total is not None else line_discount_sum
    if effective_discount is None:
        effective_discount = Decimal('0.00')
    net_sum = (gross_sum + effective_discount).quantize(Decimal('0.01'))
    return gross_sum.quantize(Decimal('0.01')), effective_discount.quantize(Decimal('0.01')), net_sum


def _totals_match_receipt_lines(
    total_amount: Decimal | None,
    lines: list[dict[str, Any]],
    discount_total: Decimal | None = None,
    tolerance: Decimal = Decimal('0.05'),
    *,
    parse_decimal: ParseDecimal,
) -> bool:
    if total_amount is None or not lines:
        return False
    _, _, net_sum = _receipt_line_financials(lines, discount_total, parse_decimal=parse_decimal)
    try:
        return abs(net_sum - Decimal(total_amount).quantize(Decimal('0.01'))) <= tolerance
    except Exception:
        return False


def _discount_or_free_total_zero_case(
    total_amount: Decimal | None,
    lines: list[dict[str, Any]],
    discount_total: Decimal | None = None,
    *,
    parse_decimal: ParseDecimal,
) -> bool:
    if total_amount is None:
        return False
    try:
        if Decimal(total_amount).quantize(Decimal('0.01')) != Decimal('0.00'):
            return False
    except Exception:
        return False
    gross_sum, _effective_discount, net_sum = _receipt_line_financials(
        lines,
        discount_total,
        parse_decimal=parse_decimal,
    )
    return bool(lines) and gross_sum >= Decimal('0.00') and abs(net_sum) <= Decimal('0.05')
