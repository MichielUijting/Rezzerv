from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


def parse_decimal_reference(raw: str | None) -> Decimal | None:
    """Reference copy of receipt_service._parse_decimal for R7b-16b.

    This script intentionally does not import backend modules. It freezes the
    current decimal parsing behavior before R7b-17 moves the helper to
    receipt_ingestion.amounts.
    """
    if not raw:
        return None
    value = raw.replace('€', '').replace('EUR', '').replace('eur', '').strip()
    value = value.replace('.', '').replace(',', '.') if ',' in value and '.' in value else value.replace(',', '.')
    value = re.sub(r'[^0-9\-.]', '', value)
    if not value or value in {'-', '.', '-.'}:
        return None
    try:
        return Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def main() -> int:
    cases = [
        ('1,23', Decimal('1.23')),
        ('1.23', Decimal('1.23')),
        ('1.234,56', Decimal('1234.56')),
        ('€ 4,99', Decimal('4.99')),
        ('-1,20', Decimal('-1.20')),
        ('abc', None),
        ('-.', None),
        (None, None),
    ]

    failures: list[str] = []
    for raw, expected in cases:
        actual = parse_decimal_reference(raw)
        if actual != expected:
            failures.append(f'parse_decimal_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    if failures:
        print('R7b-16b parse_decimal sanity check failed:')
        for failure in failures:
            print('-', failure)
        return 1

    print('R7b-16b parse_decimal sanity check passed.')
    print('No backend or SQLAlchemy dependencies imported.')
    print('Current _parse_decimal behavior is frozen for R7b-17 extraction.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
