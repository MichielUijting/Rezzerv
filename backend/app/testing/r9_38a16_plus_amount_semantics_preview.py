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
PAYMENT_OR_TOTAL_TOKENS = (
    'totaal', 'subtotaal', 'betaling', 'bankpas', 'pin', 'btw', 'terminal',
    'transactie', 'autorisatie', 'kaart', 'merchant', 'contactless', 'contactloos',
    'klantticket', 'datum', 'leesmethode', 'periode', 'saldo', 'wisselgeld', 'kassa',
)
DISCOUNT_OR_ACTION_TOKENS = (
    'plus geeft', 'voordeel', 'korting', 'actie', 'prijsvoordeel', 'zegel', 'zegels', 'pluspunten'
)
NOISE_TOKENS = {'x', 'X', '*', 'A'}


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
    tokens = [token.strip() for token in re.split(r'\s+', text.strip()) if token.strip()]
    return [token for token in tokens if token not in NOISE_TOKENS and not re.fullmatch(r'\d+x?|\d+', token.lower())]


def _stored_matches(raw_line: str, stored_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_norm = _norm(raw_line)
    result = []
    for row in stored_lines:
        label = _line_label(row)
        label_norm = _norm(label)
        if not label_norm:
            continue
        label_parts = [part for part in label_norm.split() if len(part) >= 3]
        score = 0.0
        if label_norm in raw_norm:
            score = 1.0
        elif label_parts:
            hit_ratio = sum(1 for part in label_parts if part in raw_norm) / len(label_parts)
            if hit_ratio >= 0.5:
                score = round(hit_ratio, 2)
        if score > 0:
            result.append({'score': score, **_stored_line_summary(row)})
    return sorted(result, key=lambda item: (-item['score'], item.get('line_index') or 0))


def _label_text(tokens: list[str]) -> str:
    return re.sub(r'\s+', ' ', ' '.join(tokens)).strip(' ,;:-')


def _classify_semantics(raw_line: str, stored_lines: list[dict[str, Any]], expected_total: Decimal, actual_line_sum: Decimal) -> dict[str, Any]:
    lowered = raw_line.lower()
    amounts = _amounts(raw_line)
    positive_amounts = [amount for amount in amounts if amount > Decimal('0')]
    negative_amounts = [amount for amount in amounts if amount < Decimal('0')]
    amount_values = [float(amount) for amount in amounts]
    tokens = _tokens_before_first_amount(raw_line)
    label = _label_text(tokens)
    stored = _stored_matches(raw_line, stored_lines)
    reasons: list[str] = []
    candidate_lines: list[dict[str, Any]] = []
    semantic_classification = 'unsafe_cluster'
    recommended_action = 'needs_manual_rule'
    confidence = 0.35

    has_payment_or_total = any(token in lowered for token in PAYMENT_OR_TOTAL_TOKENS)
    has_discount_or_action = any(token in lowered for token in DISCOUNT_OR_ACTION_TOKENS)
    has_non_product_label = _looks_like_non_product_receipt_label(label) if label else True

    if has_payment_or_total:
        semantic_classification = 'payment_or_total_context'
        recommended_action = 'ignore'
        confidence = 0.95
        reasons.append('contains payment/total/tax token')
    elif has_discount_or_action or negative_amounts:
        semantic_classification = 'discount_or_action_context'
        recommended_action = 'keep_existing'
        confidence = 0.85
        reasons.append('contains discount/action token or negative amount')
    elif not amounts:
        semantic_classification = 'unsafe_cluster'
        recommended_action = 'ignore'
        confidence = 0.8
        reasons.append('no amount candidates')
    elif has_non_product_label:
        semantic_classification = 'payment_or_total_context'
        recommended_action = 'ignore'
        confidence = 0.8
        reasons.append('label rejected by generic non-product guard')
    elif len(positive_amounts) == 1:
        amount = positive_amounts[0]
        if amount == expected_total or amount > expected_total * Decimal('0.80'):
            semantic_classification = 'unsafe_cluster'
            recommended_action = 'needs_manual_rule'
            confidence = 0.75
            reasons.append('single amount looks like receipt total or cluster total')
        else:
            semantic_classification = 'multi_article_candidates' if len(tokens) >= 4 else 'single_article_gross_net'
            recommended_action = 'keep_existing' if stored else 'add_missing_article'
            confidence = 0.7 if stored else 0.55
            reasons.append('single positive amount below receipt total')
            candidate_lines.append({'label': label, 'amount': float(amount), 'role': 'article_price'})
    elif len(positive_amounts) == 2:
        low, high = sorted(positive_amounts)
        if high > expected_total * Decimal('0.80'):
            semantic_classification = 'unsafe_cluster'
            recommended_action = 'needs_manual_rule'
            confidence = 0.7
            reasons.append('one amount looks like total/cluster amount')
        elif len(tokens) <= 3:
            semantic_classification = 'single_article_gross_net'
            recommended_action = 'replace_line_amount' if stored else 'add_missing_article'
            confidence = 0.8
            reasons.append('short label with two amounts interpreted as gross/net or action price')
            candidate_lines.append({'label': label, 'amount': float(low), 'role': 'net_or_action_price'})
            candidate_lines.append({'label': label, 'amount': float(high), 'role': 'gross_or_reference_price'})
        else:
            midpoint = max(1, len(tokens) // 2)
            left = _label_text(tokens[:midpoint])
            right = _label_text(tokens[midpoint:])
            semantic_classification = 'multi_article_candidates'
            recommended_action = 'keep_existing' if len(stored) >= 2 else 'add_missing_article'
            confidence = 0.58
            reasons.append('long label with two amounts could be two articles, confidence limited')
            candidate_lines.extend([
                {'label': left, 'amount': float(positive_amounts[0]), 'role': 'article_price_candidate'},
                {'label': right, 'amount': float(positive_amounts[1]), 'role': 'article_price_candidate'},
            ])
    else:
        if any(amount > expected_total * Decimal('0.60') for amount in positive_amounts):
            semantic_classification = 'unsafe_cluster'
            recommended_action = 'needs_manual_rule'
            confidence = 0.75
            reasons.append('multiple amounts include likely subtotal/cluster total')
        else:
            semantic_classification = 'multi_article_candidates'
            recommended_action = 'keep_existing' if len(stored) >= len(positive_amounts) else 'needs_manual_rule'
            confidence = 0.45
            reasons.append('three or more amounts: potential article cluster but unsafe for runtime')
            split_size = max(1, len(tokens) // len(positive_amounts))
            for index, amount in enumerate(positive_amounts):
                start = index * split_size
                end = len(tokens) if index == len(positive_amounts) - 1 else (index + 1) * split_size
                candidate_lines.append({
                    'label': _label_text(tokens[start:end]),
                    'amount': float(amount),
                    'role': 'article_price_candidate_unsafe',
                })

    candidate_sum = sum((Decimal(str(item['amount'])) for item in candidate_lines if item.get('role') != 'gross_or_reference_price'), Decimal('0')).quantize(Decimal('0.01'))
    stored_sum = sum((_line_amount(row) for row in stored_lines for item in stored if item.get('line_index') == row.get('line_index')), Decimal('0')).quantize(Decimal('0.01'))
    preview_total_if_replaced = (actual_line_sum - stored_sum + candidate_sum).quantize(Decimal('0.01'))

    return {
        'raw_ocr_line': raw_line,
        'amount_candidates': _amount_tokens(raw_line),
        'amount_values': amount_values,
        'semantic_classification': semantic_classification,
        'recommended_action': recommended_action,
        'confidence': confidence,
        'reason': reasons,
        'current_stored_lines_from_same_source': stored,
        'candidate_lines_with_semantics': candidate_lines,
        'candidate_effect': {
            'candidate_net_article_sum': float(candidate_sum),
            'current_supported_sum': float(stored_sum),
            'actual_total_before_preview': float(actual_line_sum.quantize(Decimal('0.01'))),
            'candidate_total_if_replaced': float(preview_total_if_replaced),
            'delta_to_expected_total_if_replaced': float((preview_total_if_replaced - expected_total).quantize(Decimal('0.01'))),
        },
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
            actual_line_sum = _to_decimal(actual.get('net_line_sum_used_for_decision')) or Decimal('0')
            amount_lines = [line for line in paddle_lines if _amount_tokens(line)]
            semantic_previews = [
                _classify_semantics(line, stored_lines, expected_total, actual_line_sum)
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
                'amount_semantics_preview': semantic_previews,
            })
    return {
        'test': 'R9-38A16 PLUS amount semantics preview',
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
