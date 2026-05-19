from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
import re


@dataclass
class ReceiptParseResultReference:
    is_receipt: bool
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    lines: list[dict[str, Any]] | None = None


def parse_decimal_reference(raw: str | None) -> Decimal | None:
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


def normalize_fingerprint_text_reference(value: Any) -> str:
    normalized = re.sub(r'\s+', ' ', str(value or '').strip().lower())
    normalized = re.sub(r'[^a-z0-9€.,:;\-_/ ]+', '', normalized)
    return normalized.strip()


def is_plausible_purchase_at_reference(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return False
    current_year = datetime.utcnow().year
    return current_year - 10 <= parsed.year <= current_year + 1


def is_plausible_total_amount_reference(value: Decimal | None) -> bool:
    if value is None:
        return False
    try:
        amount = Decimal(value).quantize(Decimal('0.01'))
    except Exception:
        return False
    return Decimal('0.00') <= amount <= Decimal('10000.00')


def build_receipt_fingerprint_reference(
    store_name: str | None,
    purchase_at: str | None,
    total_amount: Decimal | None,
    lines: list[dict[str, Any]],
) -> str:
    store_part = normalize_fingerprint_text_reference(store_name)
    purchase_part = ''
    if purchase_at:
        try:
            purchase_part = datetime.fromisoformat(str(purchase_at).replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
        except Exception:
            purchase_part = normalize_fingerprint_text_reference(purchase_at)
    total_part = f"{Decimal(total_amount).quantize(Decimal('0.01')):.2f}" if total_amount is not None else ''
    line_parts: list[str] = []
    for line in lines[:12]:
        label = normalize_fingerprint_text_reference(line.get('normalized_label') or line.get('raw_label'))
        if not label:
            continue
        amount = parse_decimal_reference(str(line.get('line_total')))
        amount_part = f"{amount:.2f}" if amount is not None else ''
        line_parts.append(f"{label}|{amount_part}")
    return '||'.join([store_part, purchase_part, total_part, '##'.join(line_parts)])


def build_receipt_fingerprint_from_parse_result_reference(parse_result: ReceiptParseResultReference | None) -> str:
    if not parse_result or not parse_result.is_receipt:
        return ''
    purchase_at = parse_result.purchase_at if is_plausible_purchase_at_reference(parse_result.purchase_at) else None
    total_amount = parse_result.total_amount if is_plausible_total_amount_reference(parse_result.total_amount) else None
    return build_receipt_fingerprint_reference(parse_result.store_name, purchase_at, total_amount, parse_result.lines or [])


def main() -> int:
    failures: list[str] = []

    normalize_cases = [
        ('  Albert   Heijn!  ', 'albert heijn'),
        ('Crème brûlée € 1,23', 'crme brle € 1,23'),
        ('A/B:C;D-1_2', 'a/b:c;d-1_2'),
    ]
    for raw, expected in normalize_cases:
        actual = normalize_fingerprint_text_reference(raw)
        if actual != expected:
            failures.append(f'normalize_fingerprint_text_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    plausible_date_cases = [
        ('2026-05-19T12:34:00', True),
        ('2026-05-19T12:34:00Z', True),
        ('1999-01-01T00:00:00', False),
        ('not-a-date', False),
        (None, False),
    ]
    for raw, expected in plausible_date_cases:
        actual = is_plausible_purchase_at_reference(raw)
        if actual != expected:
            failures.append(f'is_plausible_purchase_at_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    plausible_total_cases = [
        (Decimal('0.00'), True),
        (Decimal('12.34'), True),
        (Decimal('10000.00'), True),
        (Decimal('-0.01'), False),
        (Decimal('10000.01'), False),
        (None, False),
    ]
    for raw, expected in plausible_total_cases:
        actual = is_plausible_total_amount_reference(raw)
        if actual != expected:
            failures.append(f'is_plausible_total_amount_reference({raw!r}) -> {actual!r}, expected {expected!r}')

    base_lines = [
        {'normalized_label': 'Melk halfvol', 'line_total': '1,29'},
        {'raw_label': 'Brood volkoren', 'line_total': '2.50'},
        {'normalized_label': '', 'raw_label': '  ', 'line_total': '9,99'},
        {'raw_label': 'Bananen', 'line_total': '€ 3,10'},
    ]
    expected_fingerprint = 'jumbo||2026-05-19 12:34||6.89||melk halfvol|1.29##brood volkoren|2.50##bananen|3.10'
    actual_fingerprint = build_receipt_fingerprint_reference(
        'Jumbo',
        '2026-05-19T12:34:56',
        Decimal('6.89'),
        base_lines,
    )
    if actual_fingerprint != expected_fingerprint:
        failures.append(f'build_receipt_fingerprint_reference(...) -> {actual_fingerprint!r}, expected {expected_fingerprint!r}')

    overflow_lines = [{'raw_label': f'Artikel {index}', 'line_total': '1,00'} for index in range(15)]
    overflow_fingerprint = build_receipt_fingerprint_reference('Lidl', None, None, overflow_lines)
    expected_line_count = 12
    actual_line_count = len(overflow_fingerprint.split('||')[-1].split('##'))
    if actual_line_count != expected_line_count:
        failures.append(f'fingerprint line cap -> {actual_line_count}, expected {expected_line_count}')

    valid_result = ReceiptParseResultReference(
        is_receipt=True,
        store_name='Albert Heijn',
        purchase_at='2026-05-19T08:01:00',
        total_amount=Decimal('4.20'),
        lines=[{'raw_label': 'Koffie', 'line_total': '4,20'}],
    )
    expected_from_result = 'albert heijn||2026-05-19 08:01||4.20||koffie|4.20'
    actual_from_result = build_receipt_fingerprint_from_parse_result_reference(valid_result)
    if actual_from_result != expected_from_result:
        failures.append(f'build_receipt_fingerprint_from_parse_result_reference(valid) -> {actual_from_result!r}, expected {expected_from_result!r}')

    invalid_result = ReceiptParseResultReference(
        is_receipt=True,
        store_name='AH',
        purchase_at='1999-01-01T00:00:00',
        total_amount=Decimal('10000.01'),
        lines=[{'raw_label': 'Thee', 'line_total': '1,00'}],
    )
    expected_invalid_result = 'ah||||||thee|1.00'
    actual_invalid_result = build_receipt_fingerprint_from_parse_result_reference(invalid_result)
    if actual_invalid_result != expected_invalid_result:
        failures.append(f'build_receipt_fingerprint_from_parse_result_reference(invalid fields) -> {actual_invalid_result!r}, expected {expected_invalid_result!r}')

    not_receipt_result = ReceiptParseResultReference(
        is_receipt=False,
        store_name='Jumbo',
        purchase_at='2026-05-19T12:00:00',
        total_amount=Decimal('1.00'),
        lines=[{'raw_label': 'Item', 'line_total': '1,00'}],
    )
    actual_not_receipt = build_receipt_fingerprint_from_parse_result_reference(not_receipt_result)
    if actual_not_receipt != '':
        failures.append(f'build_receipt_fingerprint_from_parse_result_reference(non-receipt) -> {actual_not_receipt!r}, expected empty string')

    if failures:
        print('R7b-19 fingerprint helper sanity check failed:')
        for failure in failures:
            print('-', failure)
        return 1

    print('R7b-19 fingerprint helper sanity check passed.')
    print('No backend, SQLAlchemy, OCR, or app service dependencies imported.')
    print('Current fingerprint helper behavior is frozen for later extraction.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
