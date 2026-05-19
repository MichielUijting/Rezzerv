from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
AMOUNTS = ROOT / 'backend' / 'app' / 'receipt_ingestion' / 'amounts.py'

service = RECEIPT_SERVICE.read_text(encoding='utf-8')
amounts = AMOUNTS.read_text(encoding='utf-8')

old_helper = """\ndef _parse_decimal(raw: str | None) -> Decimal | None:\n    if not raw:\n        return None\n    value = raw.replace('€', '').replace('EUR', '').replace('eur', '').strip()\n    value = value.replace('.', '').replace(',', '.') if ',' in value and '.' in value else value.replace(',', '.')\n    value = re.sub(r'[^0-9\\-.]', '', value)\n    if not value or value in {'-', '.', '-.'}:\n        return None\n    try:\n        return Decimal(value).quantize(Decimal('0.01'))\n    except (InvalidOperation, ValueError):\n        return None\n\n\n"""

if old_helper not in service:
    raise SystemExit('Expected local _parse_decimal helper not found in receipt_service.py')

import_line = 'from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal\n'
if import_line not in service:
    marker = 'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n'
    if marker not in service:
        raise SystemExit('Import marker for receipt_ingestion.normalization not found')
    service = service.replace(marker, marker + import_line, 1)

service = service.replace(old_helper, '', 1)
RECEIPT_SERVICE.write_text(service, encoding='utf-8')

old_amounts_parse_decimal = """\ndef parse_decimal(value: object) -> Decimal | None:\n    \"\"\"Parse an OCR amount-like value into a 2-decimal Decimal.\n\n    This helper is deliberately status-neutral: invalid values return None and\n    no parser, UI, or PO status is derived here.\n    \"\"\"\n    if value is None:\n        return None\n\n    cleaned = str(value).strip()\n    if not cleaned:\n        return None\n\n    cleaned = cleaned.replace('€', '').replace('EUR', '').replace('eur', '').replace('\\xa0', ' ').strip()\n    cleaned = re.sub(r'[^0-9,.-]', '', cleaned)\n    if not cleaned or cleaned in {'-', ',', '.', '-,', '-.'}:\n        return None\n\n    if ',' in cleaned and '.' in cleaned:\n        if cleaned.rfind(',') > cleaned.rfind('.'):\n            cleaned = cleaned.replace('.', '').replace(',', '.')\n        else:\n            cleaned = cleaned.replace(',', '')\n    else:\n        cleaned = cleaned.replace(',', '.')\n\n    try:\n        return Decimal(cleaned).quantize(Decimal('0.01'))\n    except (InvalidOperation, ValueError):\n        return None\n\n"""

new_amounts_parse_decimal = """\ndef parse_decimal(raw: str | None) -> Decimal | None:\n    \"\"\"Parse an OCR amount-like value into a 2-decimal Decimal.\n\n    This is the R7b-16b frozen behavior extracted from receipt_service._parse_decimal.\n    The helper is deliberately status-neutral: invalid values return None.\n    \"\"\"\n    if not raw:\n        return None\n    value = raw.replace('€', '').replace('EUR', '').replace('eur', '').strip()\n    value = value.replace('.', '').replace(',', '.') if ',' in value and '.' in value else value.replace(',', '.')\n    value = re.sub(r'[^0-9\\-.]', '', value)\n    if not value or value in {'-', '.', '-.'}:\n        return None\n    try:\n        return Decimal(value).quantize(Decimal('0.01'))\n    except (InvalidOperation, ValueError):\n        return None\n\n"""

if old_amounts_parse_decimal not in amounts:
    raise SystemExit('Expected existing parse_decimal helper not found in amounts.py')
amounts = amounts.replace(old_amounts_parse_decimal, new_amounts_parse_decimal, 1)
AMOUNTS.write_text(amounts, encoding='utf-8')

print('R7b-17 patch applied: parse_decimal extracted and receipt_service wired via import alias.')
