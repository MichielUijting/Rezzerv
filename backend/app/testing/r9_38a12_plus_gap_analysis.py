from __future__ import annotations

import json
import re
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.receipt_status_baseline_service import (
    _fetch_active_actual_rows,
    _to_decimal,
    load_expected_receipt_statuses,
)

TARGET_PATTERNS = (
    'plus foto 1',
    'plus foto 2',
)


def _norm(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _money(value: Any) -> float | None:
    dec = _to_decimal(value)
    if dec is None:
        return None
    return float(dec.quantize(Decimal('0.01')))


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _norm(left), _norm(right)).ratio()


def _fetch_lines(conn, receipt_table_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            '''
            SELECT
                id,
                line_index,
                raw_label,
                normalized_label,
                corrected_raw_label,
                quantity,
                unit,
                unit_price,
                line_total,
                corrected_line_total,
                discount_amount,
                confidence_score,
                article_match_status,
                is_deleted,
                is_validated
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
            ORDER BY line_index, id
            '''
        ),
        {'receipt_table_id': receipt_table_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _line_label(row: dict[str, Any]) -> str:
    return str(row.get('corrected_raw_label') or row.get('raw_label') or row.get('normalized_label') or '').strip()


def _line_amount(row: dict[str, Any]) -> Decimal:
    return _to_decimal(row.get('corrected_line_total')) or _to_decimal(row.get('line_total')) or Decimal('0')


def _line_discount(row: dict[str, Any]) -> Decimal:
    return _to_decimal(row.get('discount_amount')) or Decimal('0')


def _classify_actual_line(row: dict[str, Any], receipt_total: Decimal | None) -> list[str]:
    label = _line_label(row)
    lowered = label.lower()
    line_total = _line_amount(row)
    discount = _line_discount(row)
    flags: list[str] = []
    if row.get('is_deleted'):
        flags.append('deleted')
    if discount != 0:
        flags.append('has_line_discount')
    if line_total < 0:
        flags.append('negative_line_total')
    if receipt_total is not None and abs(line_total) == abs(receipt_total) and receipt_total != 0:
        flags.append('equals_receipt_total')
    if any(token in lowered for token in ('korting', 'voordeel', 'actie', 'bonus', 'prijsvoordeel')):
        flags.append('discount_or_promo_text')
    if any(token in lowered for token in ('totaal', 'subtotaal', 'te betalen', 'betaling', 'bankpas', 'pin')):
        flags.append('payment_or_total_text')
    if any(token in lowered for token in ('statiegeld', 'emballage', 'retour')):
        flags.append('deposit_or_return_text')
    if re.fullmatch(r'[\d\s,\.:%/\-+xX]+', label):
        flags.append('numeric_only_label')
    if len(label) > 70:
        flags.append('very_long_label')
    return flags


def _summarize_actual_lines(rows: list[dict[str, Any]], receipt_total: Decimal | None) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        line_total = _line_amount(row)
        discount = _line_discount(row)
        result.append(
            {
                'line_index': row.get('line_index'),
                'raw_label': row.get('raw_label'),
                'normalized_label': row.get('normalized_label'),
                'line_total': float(line_total.quantize(Decimal('0.01'))),
                'discount_amount': float(discount.quantize(Decimal('0.01'))),
                'net_line_total': float((line_total + discount).quantize(Decimal('0.01'))),
                'quantity': float(row['quantity']) if row.get('quantity') is not None else None,
                'unit_price': float(row['unit_price']) if row.get('unit_price') is not None else None,
                'confidence_score': float(row['confidence_score']) if row.get('confidence_score') is not None else None,
                'article_match_status': row.get('article_match_status'),
                'is_deleted': row.get('is_deleted'),
                'flags': _classify_actual_line(row, receipt_total),
            }
        )
    return result


def _rank_false_positive_candidates(rows: list[dict[str, Any]], receipt_total: Decimal | None) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        flags = _classify_actual_line(row, receipt_total)
        line_total = _line_amount(row)
        score = 0
        for flag in flags:
            score += {
                'payment_or_total_text': 8,
                'discount_or_promo_text': 5,
                'equals_receipt_total': 5,
                'deposit_or_return_text': 4,
                'numeric_only_label': 4,
                'very_long_label': 2,
                'negative_line_total': 2,
                'has_line_discount': 1,
            }.get(flag, 0)
        if line_total > Decimal('8.00'):
            score += 1
        if score <= 0:
            continue
        candidates.append(
            {
                'line_index': row.get('line_index'),
                'label': _line_label(row),
                'line_total': float(line_total.quantize(Decimal('0.01'))),
                'discount_amount': _money(row.get('discount_amount')),
                'flags': flags,
                'suspicion_score': score,
            }
        )
    return sorted(candidates, key=lambda item: (-item['suspicion_score'], item['line_index'] or 0))


def _fetch_source_text(conn, raw_receipt_id: str | None) -> list[str]:
    if not raw_receipt_id:
        return []
    possible_columns = [
        'ocr_text',
        'raw_text',
        'source_text',
        'extracted_text',
        'text_content',
    ]
    cols = {str(row[1]) for row in conn.execute(text('PRAGMA table_info(raw_receipts)')).fetchall()}
    selected = [col for col in possible_columns if col in cols]
    if not selected:
        return []
    select_expr = ', '.join(selected)
    row = conn.execute(text(f'SELECT {select_expr} FROM raw_receipts WHERE id = :id'), {'id': raw_receipt_id}).mappings().first()
    if not row:
        return []
    text_parts = [str(row.get(col) or '') for col in selected if row.get(col)]
    text_value = '\n'.join(text_parts)
    return [re.sub(r'\s+', ' ', line).strip() for line in text_value.splitlines() if re.sub(r'\s+', ' ', line).strip()]


def _source_text_gap_candidates(source_lines: list[str], actual_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual_labels = [_line_label(row) for row in actual_lines]
    candidates = []
    amount_re = re.compile(r'-?\d{1,6}(?:[\.,]\d{2})')
    for index, line in enumerate(source_lines):
        lowered = line.lower()
        if any(token in lowered for token in ('totaal', 'subtotaal', 'betaling', 'bankpas', 'pin', 'btw', 'terminal', 'transactie')):
            continue
        if not amount_re.search(line):
            continue
        best_ratio = max((_ratio(line, label) for label in actual_labels), default=0.0)
        if best_ratio >= 0.78:
            continue
        candidates.append(
            {
                'source_index': index,
                'text': line,
                'best_existing_label_similarity': round(best_ratio, 3),
                'reason': 'amount-bearing source line not close to stored article label',
            }
        )
    return candidates[:30]


def _discount_or_correction_candidates(source_lines: list[str], actual_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    amount_re = re.compile(r'-?\d{1,6}(?:[\.,]\d{2})')
    for index, line in enumerate(source_lines):
        lowered = line.lower()
        if not any(token in lowered for token in ('korting', 'voordeel', 'actie', 'bonus', 'prijsvoordeel', 'statiegeld', 'emballage', 'retour')):
            continue
        matches = amount_re.findall(line)
        candidates.append(
            {
                'source_index': index,
                'text': line,
                'amount_candidates': matches,
                'reason': 'source line looks like discount/correction/deposit candidate',
            }
        )
    for row in actual_lines:
        flags = _classify_actual_line(row, None)
        if 'has_line_discount' in flags or 'discount_or_promo_text' in flags or 'deposit_or_return_text' in flags:
            candidates.append(
                {
                    'line_index': row.get('line_index'),
                    'text': _line_label(row),
                    'line_total': _money(row.get('line_total')),
                    'discount_amount': _money(row.get('discount_amount')),
                    'reason': 'stored article line has discount/correction/deposit signal',
                }
            )
    return candidates[:30]


def _baseline_for_plus() -> list[dict[str, Any]]:
    result = []
    for row in load_expected_receipt_statuses():
        source = str(row.get('source_file') or '').lower()
        if any(pattern in source for pattern in TARGET_PATTERNS):
            result.append(dict(row))
    return result


def build_report() -> dict[str, Any]:
    with engine.connect() as conn:
        actual_rows = _fetch_active_actual_rows(conn, household_id='1')
        expected_rows = _baseline_for_plus()
        reports = []
        for expected in expected_rows:
            expected_source = _norm(expected.get('source_file'))
            actual = next(
                (
                    row
                    for row in actual_rows
                    if _norm(row.get('original_filename')) == expected_source
                ),
                None,
            )
            if actual is None:
                reports.append({'source_file': expected.get('source_file'), 'status': 'missing_actual_receipt'})
                continue
            receipt_total = _to_decimal(actual.get('total_amount'))
            lines = _fetch_lines(conn, str(actual.get('receipt_table_id')))
            source_lines = _fetch_source_text(conn, actual.get('raw_receipt_id'))
            gross = sum((_line_amount(row) for row in lines if not row.get('is_deleted')), Decimal('0')).quantize(Decimal('0.01'))
            line_discount = sum((_line_discount(row) for row in lines if not row.get('is_deleted')), Decimal('0')).quantize(Decimal('0.01'))
            receipt_discount = _to_decimal(actual.get('discount_total')) or Decimal('0')
            net = _to_decimal(actual.get('net_line_sum_used_for_decision')) or (gross + line_discount).quantize(Decimal('0.01'))
            reports.append(
                {
                    'source_file': expected.get('source_file'),
                    'matched_original_filename': actual.get('original_filename'),
                    'receipt_table_id': actual.get('receipt_table_id'),
                    'raw_receipt_id': actual.get('raw_receipt_id'),
                    'expected_total_amount': _money(expected.get('total_amount')),
                    'total_amount': _money(actual.get('total_amount')),
                    'expected_line_count': expected.get('line_count'),
                    'actual_line_count': actual.get('line_count'),
                    'gross_line_sum': float(gross),
                    'line_discount_sum': float(line_discount),
                    'receipt_discount_total': float(receipt_discount.quantize(Decimal('0.01'))),
                    'net_line_sum': float(net.quantize(Decimal('0.01'))),
                    'line_count_gap': int(expected.get('line_count') or 0) - int(actual.get('line_count') or 0),
                    'line_sum_gap_to_total': float((net - (receipt_total or Decimal('0'))).quantize(Decimal('0.01'))),
                    'stored_article_lines': _summarize_actual_lines(lines, receipt_total),
                    'false_positive_article_candidates': _rank_false_positive_candidates(lines, receipt_total),
                    'missing_article_candidates': _source_text_gap_candidates(source_lines, lines),
                    'discount_or_correction_candidates': _discount_or_correction_candidates(source_lines, lines),
                    'source_text_available': bool(source_lines),
                    'source_text_line_count': len(source_lines),
                    'read_only': True,
                }
            )
    return {
        'test': 'R9-38A12 PLUS foto 1/foto 2 read-only gap analysis',
        'household_id': '1',
        'target_patterns': TARGET_PATTERNS,
        'reports': reports,
        'read_only': True,
    }


def main() -> int:
    print(json.dumps(build_report(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
