from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'

source = TARGET.read_text(encoding='utf-8-sig')
required_markers = [
    'def _parse_decimal(',
    'def _parse_quantity(',
    'def _amount_to_float(',
    'def _price_from_split_parts(',
]
missing = [marker for marker in required_markers if marker not in source]
if missing:
    raise SystemExit(f'Missing amount helper(s) in receipt_service.py: {missing}')

# Standalone behavioural mirror of the current helpers. This deliberately avoids
# importing receipt_service.py, because local user machines do not necessarily
# have backend dependencies such as SQLAlchemy installed.
def parse_quantity(raw: str | None) -> Decimal | None:
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


def parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace('€', '').replace('\xa0', ' ').strip()
    cleaned = re.sub(r'[^0-9,.-]', '', cleaned)
    if not cleaned or cleaned in {'-', ',', '.', '-,', '-.'}:
        return None
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    else:
        cleaned = cleaned.replace(',', '.')
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def amount_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def price_from_split_parts(euros: str | None, cents: str | None) -> Decimal | None:
    if euros is None or cents is None:
        return None
    try:
        return Decimal(f"{int(euros)}.{int(cents):02d}").quantize(Decimal('0.01'))
    except Exception:
        return None

cases_parse_decimal = [
    ('1,23', Decimal('1.23')),
    ('1.23', Decimal('1.23')),
    ('€ 1,23', Decimal('1.23')),
    ('1.234,56', Decimal('1234.56')),
    ('1,234.56', Decimal('1234.56')),
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
    print('R7b-13b standalone amount helper sanity check failed:')
    for failure in failures:
        print('-', failure)
    raise SystemExit(1)

print('R7b-13b standalone amount helper sanity check passed.')
print('No backend dependencies imported; safe to run on local Windows Python.')
