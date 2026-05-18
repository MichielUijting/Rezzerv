from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b15')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_line = (
    'from app.receipt_ingestion.amounts import (\n'
    '    amount_to_float,\n'
    '    parse_quantity,\n'
    '    price_from_split_parts,\n'
    ')\n'
)

if 'from app.receipt_ingestion.amounts import (' not in content:
    anchor = 'from app.receipt_ingestion.normalization import normalize_text_lines\n'
    fallback_anchor = 'from app.receipt_ingestion.generic_text_parser import route_generic_text_parser\n'
    if anchor in content:
        content = content.replace(anchor, anchor + import_line, 1)
    elif fallback_anchor in content:
        content = content.replace(fallback_anchor, fallback_anchor + import_line, 1)
    else:
        raise SystemExit('R7b-15 aborted: no safe receipt_ingestion import anchor found.')

# Replace usages first.
replacements = {
    '_amount_to_float(': 'amount_to_float(',
    '_parse_quantity(': 'parse_quantity(',
    '_price_from_split_parts(': 'price_from_split_parts(',
}
for old, new in replacements.items():
    content = content.replace(old, new)

patterns = [
    re.compile(
        r"\n\ndef amount_to_float\(value: Decimal \| None\) -> float \| None:.*?return float\(value\) if value is not None else None\n",
        re.DOTALL,
    ),
    re.compile(
        r"\n\ndef _amount_to_float\(value: Decimal \| None\) -> float \| None:.*?return float\(value\) if value is not None else None\n",
        re.DOTALL,
    ),
    re.compile(
        r"\n\ndef parse_quantity\(raw: str \| None\) -> Decimal \| None:.*?except \(InvalidOperation, ValueError\):\n\s+return None\n",
        re.DOTALL,
    ),
    re.compile(
        r"\n\ndef _parse_quantity\(raw: str \| None\) -> Decimal \| None:.*?except \(InvalidOperation, ValueError\):\n\s+return None\n",
        re.DOTALL,
    ),
    re.compile(
        r"\n\ndef price_from_split_parts\(euros: str \| None, cents: str \| None\) -> Decimal \| None:.*?except Exception:\n\s+return None\n",
        re.DOTALL,
    ),
    re.compile(
        r"\n\ndef _price_from_split_parts\(euros: str \| None, cents: str \| None\) -> Decimal \| None:.*?except Exception:\n\s+return None\n",
        re.DOTALL,
    ),
]

removed = 0
for pattern in patterns:
    content, count = pattern.subn('\n', content, count=1)
    removed += count

if removed == 0:
    raise SystemExit('R7b-15 aborted: no local amount helper definitions removed.')

# Guards.
for forbidden in [
    '_amount_to_float(',
    '_parse_quantity(',
    '_price_from_split_parts(',
    'def amount_to_float(value: Decimal | None)',
    'def parse_quantity(raw: str | None)',
    'def price_from_split_parts(euros: str | None, cents: str | None)',
]:
    if forbidden in content:
        raise SystemExit(f'R7b-15 guard failed: leftover helper marker {forbidden!r}')

TARGET.write_text(content, encoding='utf-8')
print('R7b-15 amount helper wiring applied to', TARGET)
print('Backup written to', BACKUP)
