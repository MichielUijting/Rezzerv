from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.parsing.line_classification_helpers import _looks_like_non_product_receipt_label
from app.receipt_ingestion.service_parts.image_ocr_flow import _ocr_image_text_with_paddle
from app.services.receipt_service import _resolve_reparse_source_payload
from app.services.receipt_status_baseline_service import _fetch_active_actual_rows, _to_decimal, load_expected_receipt_statuses

TARGET_PATTERNS = ('plus foto 1', 'plus foto 2')
_AMOUNT_RE = re.compile(r'-?\d{1,6}(?:[\.,]\d{2})')
_SKIP_SOURCE_TOKENS = (
    'totaal', 'subtotaal', 'betaling', 'bankpas', 'pin', 'btw', 'terminal',
    'transactie', 'autorisatie', 'kaart', 'merchant', 'contactless', 'klantticket',
    'zegel', 'pluspunten', 'datum', 'leesmethode', 'periode', 'saldo'
)
_DISCOUNT_TOKENS = ('plus geeft', 'voordeel', 'korting', 'actie', 'prijsvoordeel')
_QTY_OR_MARKER_RE = re.compile(r'^(?:\d+\s*[xX]|[xX]|[*]+|[A-Z])$')


def _norm(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _money(value: Any) -> float | None:
    dec = _to_decimal(value)
    return float(dec.quantize(Decimal('0.01'))) if dec is not None else None


def _amount_tokens(value: Any) -> list[str]:
    return _AMOUNT_RE.findall(str(value or ''))


def _amounts(value: Any) -> list[Decimal]:
    result: list[Decimal] = []
    for token in _amount_tokens(value):
        dec = _parse_decimal(token)
        if dec is not None:
            result.append(dec.quantize(Decimal('0.01')))
    return result


def _fetch_record(conn, receipt_table_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            '''
            SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rr.original_filename,
                   rr.mime_type, rr.storage_path, rem.body_html, rem.body_text,
                   rem.selected_part_type
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
            WHERE rt.id = :receipt_table_id
            LIMIT 1
            '''
        ),
        {'receipt_table_id': receipt_table_id},
    ).mappings().first()
    return dict(row) if row else None


def _fetch_lines(conn, receipt_table_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            '''
            SELECT line_index, raw_label, normalized_label, corrected_raw_label,
                   quantity, unit_price, line_total, corrected_line_total,
                   discount_amount, confidence_score, is_deleted
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


def _stored_line_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'line_index': row.get('line_index'),
        'raw_label': row.get('raw_label'),
        'line_total': _money(row.get('corrected_line_total') if row.get('corrected_line_total') is not None else row.get('line_total')),
        'discount_amount': _money(row.get('discount_amount')),
        'unit_price': _money(row.get('unit_price')),
        'quantity': float(row['quantity']) if row.get('quantity') is not None else None,
        'is_deleted': row.get('is_deleted'),
    }


def _read_paddle_lines(record: dict[str, Any]) -> list[str]:
    storage_path = Path(str(record.get('storage_path') or ''))
    if not storage_path.exists():
        return []
    file_bytes = storage_path.read_bytes()
    parse_bytes, parse_filename, _parse_mime_type = _resolve_reparse_source_payload(dict(record), file_bytes)
    lines, _confidence = _ocr_image_text_with_paddle(parse_bytes, parse_filename)
    return [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines or [] if re.sub(r'\s+', ' ', str(line or '')).strip()]


def _tokens_before_first_amount(raw_line: str) -> list[str]:
    first = _AMOUNT_RE.search(raw_line)
    text = raw_line[: first.start()] if first else raw_line
    tokens = [token for token in re.split(r'\s+', text.strip()) if token]
    return [token for token in tokens if not _QTY_OR_MARKER_RE.match(token)]


def _simple_even_split(tokens: list[str], amount_count: int) -> list[str]:
    if amount_count <= 0 or len(tokens) < amount_count:
        return []
    base = len(tokens) // amount_count
    extra = len(tokens) % amount_count
    labels = []
    cursor = 0
    for index in range(amount_count):
        size = base + (1 if index < extra else 0)
        chunk = tokens[cursor: cursor + size]
        cursor += size
        labels.append(' '.join(chunk).strip())
    return labels


def _best_stored_lines(raw_line: str, stored_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_norm = _norm(raw_line)
    result = []
    for row in stored_lines:
        label = _line_label(row)
        label_norm = _norm(label)
        if not label_norm:
            continue
        score = 0.0
        if label_norm in raw_norm:
            score = 1.0
        elif any(part and part in raw_norm for part in label_norm.split()):
            score = 0.5
        if score > 0:
            result.append({'score': score, **_stored_line_summary(row)})
    return sorted(result, key=lambda item: (-item['score'], item.get('line_index') or 0))


def _candidate_from_line(raw_line: str, stored_lines: list[dict[str, Any]], expected_total: Decimal, actual_total: Decimal) -> dict[str, Any]:
    lowered = raw_line.lower()
    amount_tokens = _amount_tokens(raw_line)
    amount_values = _amounts(raw_line)
    stored_from_source = _best_stored_lines(raw_line, stored_lines)
    rejection_reasons: list[str] = []
    if any(token in lowered for token in _SKIP_SOURCE_TOKENS):
        rejection_reasons.append('source_line_contains_non_product_or_payment_token')
    if any(token in lowered for token in _DISCOUNT_TOKENS):
        rejection_reasons.append('source_line_contains_discount_or_action_context')
    if len(amount_values) < 2:
        rejection_reasons.append('less_than_two_amounts')
    if len(amount_values) > 5:
        rejection_reasons.append('too_many_amounts_for_safe_split')
    positive_amounts = [amount for amount in amount_values if amount > Decimal('0')]
    if len(positive_amounts) != len(amount_values):
        rejection_reasons.append('contains_negative_or_zero_amount')

    tokens = _tokens_before_first_amount(raw_line)
    labels = _simple_even_split(tokens, len(positive_amounts)) if positive_amounts else []
    if len(labels) != len(positive_amounts):
        rejection_reasons.append('cannot_evenly_create_label_candidates')

    candidate_lines = []
    for label, amount in zip(labels, positive_amounts):
        clean_label = re.sub(r'^[^A-Za-z0-9]+', '', label).strip()
        if not clean_label:
            rejection_reasons.append('empty_candidate_label')
            continue
        if _looks_like_non_product_receipt_label(clean_label):
            rejection_reasons.append(f'candidate_label_rejected_as_non_product:{clean_label}')
        candidate_lines.append({
            'label': clean_label,
            'amount': float(amount),
            'raw_amount': amount_tokens[len(candidate_lines)] if len(candidate_lines) < len(amount_tokens) else None,
        })

    candidate_sum = sum((Decimal(str(item['amount'])) for item in candidate_lines), Decimal('0')).quantize(Decimal('0.01'))
    stored_sum = sum((_line_amount(row) for row in stored_lines if any((str(row.get('raw_label') or '').lower().split()[0:1]))), Decimal('0'))
    current_supported_sum = sum((_line_amount(row) for row in stored_lines if any((str(item.get('raw_label') or '') == str(row.get('raw_label') or '')) for item in stored_from_source)), Decimal('0')).quantize(Decimal('0.01'))
    would_add_count = max(0, len(candidate_lines) - len(stored_from_source))
    would_replace_count = len(stored_from_source) if candidate_lines else 0
    candidate_total_if_replaced = (actual_total - current_supported_sum + candidate_sum).quantize(Decimal('0.01'))

    return {
        'raw_ocr_line': raw_line,
        'amount_candidates': amount_tokens,
        'current_stored_lines_from_same_source': stored_from_source,
        'candidate_split_lines': candidate_lines,
        'candidate_line_sum': float(candidate_sum),
        'current_supported_sum': float(current_supported_sum),
        'actual_total_before_preview': float(actual_total.quantize(Decimal('0.01'))),
        'candidate_total_if_replaced': float(candidate_total_if_replaced),
        'delta_to_expected_total_if_replaced': float((candidate_total_if_replaced - expected_total).quantize(Decimal('0.01'))),
        'would_add_count': would_add_count,
        'would_replace_count': would_replace_count,
        'rejection_reason_per_candidate': rejection_reasons,
        'preview_only': True,
    }


def _expected_for_plus() -> list[dict[str, Any]]:
    rows = []
    for row in load_expected_receipt_statuses():
        source = str(row.get('source_file') or '').lower()
        if any(pattern in source for pattern in TARGET_PATTERNS):
            rows.append(dict(row))
    return rows


def build_report() -> dict[str, Any]:
    reports = []
    with engine.connect() as conn:
        actual_rows = _fetch_active_actual_rows(conn, household_id='1')
        for expected in _expected_for_plus():
            source_key = _norm(expected.get('source_file'))
            actual = next((row for row in actual_rows if _norm(row.get('original_filename')) == source_key), None)
            if actual is None:
                reports.append({'source_file': expected.get('source_file'), 'status': 'missing_actual_receipt'})
                continue
            record = _fetch_record(conn, str(actual.get('receipt_table_id')))
            stored_lines = _fetch_lines(conn, str(actual.get('receipt_table_id')))
            paddle_lines = _read_paddle_lines(record) if record else []
            expected_total = _to_decimal(expected.get('total_amount')) or Decimal('0')
            actual_total = _to_decimal(actual.get('net_line_sum_used_for_decision')) or Decimal('0')
            amount_lines = [line for line in paddle_lines if _amount_tokens(line)]
            previews = [
                _candidate_from_line(line, stored_lines, expected_total, actual_total)
                for line in amount_lines
            ]
            reports.append({
                'source_file': expected.get('source_file'),
                'matched_original_filename': actual.get('original_filename'),
                'receipt_table_id': actual.get('receipt_table_id'),
                'expected_total_amount': _money(expected.get('total_amount')),
                'actual_total_amount': _money(actual.get('total_amount')),
                'expected_line_count': expected.get('line_count'),
                'actual_line_count': actual.get('line_count'),
                'net_line_sum_used_for_decision': _money(actual.get('net_line_sum_used_for_decision')),
                'stored_article_lines': [_stored_line_summary(row) for row in stored_lines],
                'cluster_split_candidate_previews': previews,
            })
    return {
        'test': 'R9-38A15 PLUS cluster-split candidate preview',
        'read_only': True,
        'database_write_intent': False,
        'target_patterns': TARGET_PATTERNS,
        'reports': reports,
    }


def main() -> int:
    print(json.dumps(build_report(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
