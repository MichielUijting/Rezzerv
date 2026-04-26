from __future__ import annotations

from decimal import Decimal
from typing import Any


def determine_final_parse_status(parse_result: Any) -> str:
    """Bepaalt de definitieve database-status voor een kassabon.

    Businessregel PO:
    - een bon mag alleen als 'parsed' / Gecontroleerd worden opgeslagen als
      winkelnaam en totaalbedrag herkend zijn én de financiële controle klopt;
    - de som van de artikelregels moet gelijk zijn aan het totaalbedrag;
    - kortingen mogen alleen meetellen als ze expliciet als korting zijn herkend
      en de netto artikelsom daardoor alsnog aansluit op het totaalbedrag.
    """
    if not parse_result or not getattr(parse_result, 'is_receipt', False):
        return 'failed'

    has_store = bool(str(getattr(parse_result, 'store_name', '') or '').strip())
    has_total = getattr(parse_result, 'total_amount', None) is not None

    if not has_store or not has_total:
        return 'review_needed'

    lines = getattr(parse_result, 'lines', None) or []
    if not lines:
        return 'review_needed'

    try:
        line_sum = Decimal('0')
        line_discount_sum = Decimal('0')
        priced_line_count = 0

        for line in lines:
            if not isinstance(line, dict):
                continue

            line_total = line.get('line_total')
            if line_total is not None:
                line_sum += Decimal(str(line_total))
                priced_line_count += 1

            discount_amount = line.get('discount_amount')
            if discount_amount is not None:
                line_discount_sum += Decimal(str(discount_amount))

        if priced_line_count == 0:
            return 'review_needed'

        total_amount = Decimal(str(getattr(parse_result, 'total_amount')))
        if abs(line_sum - total_amount) <= Decimal('0.01'):
            return 'parsed'

        raw_discount_total = getattr(parse_result, 'discount_total', None)
        discount_total = raw_discount_total if raw_discount_total is not None else line_discount_sum
        discount_total = Decimal(str(discount_total or 0))

        if discount_total != 0:
            net_line_sum = line_sum - discount_total
            if abs(net_line_sum - total_amount) <= Decimal('0.01'):
                return 'parsed'
    except Exception:
        return 'review_needed'

    return 'review_needed'
