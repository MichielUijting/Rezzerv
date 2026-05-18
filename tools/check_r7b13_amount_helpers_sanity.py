from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'

spec = importlib.util.spec_from_file_location('receipt_service_for_amount_sanity', TARGET)
if spec is None or spec.loader is None:
    raise SystemExit('Could not load receipt_service.py for sanity check')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

cases_parse_decimal = [
    ('1,23', Decimal('1.23')),
    ('1.23', Decimal('1.23')),
    ('€ 1,23', Decimal('1.23')),
    ('-1,23', Decimal('-1.23')),
    ('', None),
    (None, None),
    ('abc', None),
]

cases_parse_quantity = [
    ('1', Decimal('1')),
    ('1,5', Decimal('1.5')),
    ('1.5', Decimal('1.5')),
    ('2 kg', Decimal('2')),
    ('', None),
    (None, None),
]

cases_price_from_split_parts = [
    ('1', '23', Decimal('1.23')),
    ('0', '05', Decimal('0.05')),
    ('12', '5', Decimal('12.05')),
    (None, '23', None),
    ('1', None, None),
]

failures: list[str] = []

for raw, expected in cases_parse_decimal:
    actual = module._parse_decimal(raw)
    if actual != expected:
        failures.append(f'_parse_decimal({raw!r}) -> {actual!r}, expected {expected!r}')

for raw, expected in cases_parse_quantity:
    actual = module._parse_quantity(raw)
    if actual != expected:
        failures.append(f'_parse_quantity({raw!r}) -> {actual!r}, expected {expected!r}')

for euros, cents, expected in cases_price_from_split_parts:
    actual = module._price_from_split_parts(euros, cents)
    if actual != expected:
        failures.append(f'_price_from_split_parts({euros!r}, {cents!r}) -> {actual!r}, expected {expected!r}')

amount_to_float_cases = [
    (Decimal('1.23'), 1.23),
    (None, None),
]
for raw, expected in amount_to_float_cases:
    actual = module._amount_to_float(raw)
    if actual != expected:
        failures.append(f'_amount_to_float({raw!r}) -> {actual!r}, expected {expected!r}')

if failures:
    print('R7b-13 amount helper sanity check failed:')
    for failure in failures:
        print('-', failure)
    raise SystemExit(1)

print('R7b-13 amount helper sanity check passed.')
print('Helpers covered: _parse_decimal, _parse_quantity, _amount_to_float, _price_from_split_parts')
