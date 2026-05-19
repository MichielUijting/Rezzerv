from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'receipt_ingestion' / 'amounts.py'

if not TARGET.exists():
    raise SystemExit('Missing backend/app/receipt_ingestion/amounts.py')

source = TARGET.read_text(encoding='utf-8-sig')
required_markers = [
    'def parse_decimal(',
    'def parse_quantity(',
    'def amount_to_float(',
    'def price_from_split_parts(',
]
missing = [marker for marker in required_markers if marker not in source]
if missing:
    raise SystemExit(f'Missing amount helper(s) in amounts.py: {missing}')

spec = importlib.util.spec_from_file_location('receipt_ingestion_amounts', TARGET)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

parse_decimal = module.parse_decimal
parse_quantity = module.parse_quantity
amount_to_float = module.amount_to_float
price_from_split_parts = module.price_from_split_parts

cases_parse_decimal = [
    ('1,23', Decimal('1.23')),
    ('1.23', Decimal('1.23')),
    ('€ 1,23', Decimal('1.23')),
    ('1.234,56', Decimal('1234.56')),
    ('1,234.56', Decimal('1.23')),
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
    actual = parse_decimal(raw)
    if actual != expected:
        failures.append(f'parse_decimal({raw!r}) -> {actual!r}, expected {expected!r}')

for raw, expected in cases_parse_quantity:
    actual = parse_quantity(raw)
    if actual != expected:
        failures.append(f'parse_quantity({raw!r}) -> {actual!r}, expected {expected!r}')

for euros, cents, expected in cases_price_from_split_parts:
    actual = price_from_split_parts(euros, cents)
    if actual != expected:
        failures.append(f'price_from_split_parts({euros!r}, {cents!r}) -> {actual!r}, expected {expected!r}')

for raw, expected in [(Decimal('1.23'), 1.23), (None, None)]:
    actual = amount_to_float(raw)
    if actual != expected:
        failures.append(f'amount_to_float({raw!r}) -> {actual!r}, expected {expected!r}')

if failures:
    print('R7b-17 standalone amount helper sanity check failed:')
    for failure in failures:
        print('-', failure)
    raise SystemExit(1)

print('R7b-17 standalone amount helper sanity check passed.')
print('parse_decimal extracted to receipt_ingestion.amounts.')
print('No backend dependencies imported; safe to run on local Windows Python.')
