from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


def parse_quantity_reference(raw: str | None) -> Decimal | None:
    """Reference copy of receipt_service._parse_quantity for R7b-23.

    This script intentionally does not import backend modules. It freezes the
    current amount residue helper behavior before wiring helpers through
    receipt_ingestion.amounts.
    """
    if not raw:
        return None
    cleaned = raw.strip().replace(',', '.')
    cleaned = re.sub(r'[^0-9\-.]', '', cleaned)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def amount_to_float_reference(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def price_from_split_parts_reference(euros: str | None, cents: str | None) -> Decimal | None:
    if euros is None or cents is None:
        return None
    try:
        return Decimal(f"{int(euros)}.{int(cents):02d}").quantize(Decimal('0.01'))
    except Exception:
        return None


def main() -> int:
    failures: list[str] = []

    cases_parse_quantity = [
        ('1', Decimal('1')),
        ('1,5', Decimal('1.5')),
        ('1.5', Decimal('1.5')),
        ('2 kg', Decimal('2')),
        ('abc', None),
        ('', None),
        (None, None),
    ]
    for raw, expected in cases_parse_quantity:
        actual = parse_quantity_reference(raw)
        if actual != expected:
            failures.append(f'parse_quantity_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    cases_amount_to_float = [
        (Decimal('1.23'), 1.23),
        (Decimal('0.00'), 0.0),
        (None, None),
    ]
    for raw, expected in cases_amount_to_float:
        actual = amount_to_float_reference(raw)
        if actual != expected:
            failures.append(f'amount_to_float_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    cases_price_from_split_parts = [
        ('1', '23', Decimal('1.23')),
        ('0', '05', Decimal('0.05')),
        ('12', '5', Decimal('12.05')),
        (None, '23', None),
        ('1', None, None),
        ('abc', '23', None),
    ]
    for euros, cents, expected in cases_price_from_split_parts:
        actual = price_from_split_parts_reference(euros, cents)
        if actual != expected:
            failures.append(f'price_from_split_parts_reference({euros!r}, {cents!r}) -> {actual!r}, expected {expected!r}')

    if failures:
        print('R7b-23 amount residue sanity check failed:')
        for failure in failures:
            print('-', failure)
        return 1

    print('R7b-23 amount residue sanity check passed.')
    print('No backend or SQLAlchemy dependencies imported.')
    print('Current amount residue helper behavior is frozen for R7b-24 wiring.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
