from __future__ import annotations

import json
import re
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
)
from app.services.receipt_service import _resolve_reparse_source_payload, parse_receipt_content
from app.services.receipt_status_baseline_service import (
    _fetch_active_actual_rows,
    _to_decimal,
    load_expected_receipt_statuses,
)

TARGET_PATTERNS = (
    'plus foto 1',
    'plus foto 2',
)
IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def _norm(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _money(value: Any) -> float | None:
    dec = _to_decimal(value)
    if dec is None:
        return None
    return float(dec.quantize(Decimal('0.01')))


def _decimal(value: Any) -> Decimal:
    return _to_decimal(value) or Decimal('0')


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _norm(left), _norm(right)).ratio()


def _amount_tokens(value: Any) -> list[str]:
    return re.findall(r'-?\d{1,6}(?:[\.,]\d{2})', str(value or ''))


def _amounts_as_decimal(value: Any) -> list[Decimal]:
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
            SELECT
                rt.id AS receipt_table_id,
                rt.raw_receipt_id,
                rr.household_id,
                rr.original_filename,
                rr.mime_type,
                rr.storage_path,
                rem.body_html,
                rem.body_text,
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


def _summarize_line(row: dict[str, Any]) -> dict[str, Any]:
    line_total = _line_amount(row)
    discount = _line_discount(row)
    return {
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
    }


def _summarize_parse_line(index: int, line: dict[str, Any]) -> dict[str, Any]:
    line_total = _decimal(line.get('line_total'))
    discount = _decimal(line.get('discount_amount'))
    return {
        'line_index': index,
        'raw_label': line.get('raw_label'),
        'normalized_label': line.get('normalized_label'),
        'line_total': float(line_total.quantize(Decimal('0.01'))),
        'discount_amount': float(discount.quantize(Decimal('0.01'))),
        'net_line_total': float((line_total + discount).quantize(Decimal('0.01'))),
        'quantity': line.get('quantity'),
        'unit_price': line.get('unit_price'),
        'confidence_score': line.get('confidence_score'),
        'source_index': line.get('source_index'),
        'producer_trace': line.get('producer_trace'),
    }


def _unique_lines(source: str, lines: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines or []):
        normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
        if not normalized:
            continue
        key = _norm(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({'source': source, 'source_index': index, 'text': normalized})
    return result


def _run_parserflow(record: dict[str, Any]) -> dict[str, Any]:
    storage_path = Path(str(record.get('storage_path') or ''))
    if not storage_path.exists():
        return {
            'storage_path': str(storage_path),
            'file_exists': False,
            'error': f'raw receipt file not found at {storage_path}',
        }
    file_bytes = storage_path.read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(dict(record), file_bytes)
    suffix = Path(str(parse_filename or '')).suffix.lower()
    ocr_source_lines: list[dict[str, Any]] = []
    ocr_errors: list[str] = []
    if parse_mime_type in IMAGE_MIME_TYPES or suffix in IMAGE_SUFFIXES:
        try:
            paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(parse_bytes, parse_filename)
            ocr_source_lines.extend(_unique_lines('paddle', paddle_lines or []))
        except Exception as exc:  # read-only diagnostics should not abort the whole report
            paddle_confidence = None
            ocr_errors.append(f'paddle: {type(exc).__name__}: {exc}')
        try:
            tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(parse_bytes, parse_filename)
            ocr_source_lines.extend(_unique_lines('tesseract', tesseract_lines or []))
        except Exception as exc:  # read-only diagnostics should not abort the whole report
            tesseract_confidence = None
            ocr_errors.append(f'tesseract: {type(exc).__name__}: {exc}')
    else:
        paddle_confidence = None
        tesseract_confidence = None
        try:
            decoded = parse_bytes.decode('utf-8', errors='ignore')
            ocr_source_lines.extend(_unique_lines('decoded_payload', decoded.splitlines()))
        except Exception as exc:
            ocr_errors.append(f'decode: {type(exc).__name__}: {exc}')

    parse_result = parse_receipt_content(parse_bytes, parse_filename, parse_mime_type)
    parse_lines = parse_result.lines or []
    return {
        'storage_path': str(storage_path),
        'file_exists': True,
        'parse_filename': parse_filename,
        'parse_mime_type': parse_mime_type,
        'ocr_confidence': {
            'paddle': paddle_confidence,
            'tesseract': tesseract_confidence,
        },
        'ocr_errors': ocr_errors,
        'parse_result_summary': {
            'is_receipt': parse_result.is_receipt,
            'parse_status': parse_result.parse_status,
            'store_name': parse_result.store_name,
            'purchase_at': parse_result.purchase_at,
            'total_amount': _money(parse_result.total_amount),
            'discount_total': _money(parse_result.discount_total),
            'line_count': len(parse_lines),
            'confidence_score': parse_result.confidence_score,
        },
        'raw_ocr_or_parser_text_lines': ocr_source_lines[:120],
        'parsed_result_article_lines': [
            _summarize_parse_line(index, dict(line))
            for index, line in enumerate(parse_lines)
        ],
        'parser_diagnostics': parse_result.parser_diagnostics or {},
    }


def _amount_bearing_source_lines(source_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in source_lines:
        amounts = _amount_tokens(item.get('text'))
        if not amounts:
            continue
        result.append({**item, 'amount_candidates': amounts})
    return result


def _source_lines_not_stored(source_lines: list[dict[str, Any]], stored_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stored_labels = [_line_label(row) for row in stored_lines]
    result = []
    for item in _amount_bearing_source_lines(source_lines):
        text_value = str(item.get('text') or '')
        lowered = text_value.lower()
        if any(token in lowered for token in ('totaal', 'subtotaal', 'betaling', 'bankpas', 'pin', 'btw', 'terminal', 'transactie')):
            continue
        best_label = None
        best_ratio = 0.0
        for label in stored_labels:
            ratio = _ratio(text_value, label)
            if ratio > best_ratio:
                best_ratio = ratio
                best_label = label
        if best_ratio >= 0.78:
            continue
        result.append({
            **item,
            'best_stored_label': best_label,
            'best_stored_label_similarity': round(best_ratio, 3),
            'reason': 'amount-bearing OCR/parser source line is not close to a stored article line',
        })
    return result[:40]


def _stored_lines_not_supported(source_lines: list[dict[str, Any]], stored_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_texts = [str(item.get('text') or '') for item in source_lines]
    result = []
    for row in stored_lines:
        label = _line_label(row)
        best_source = None
        best_ratio = 0.0
        for text_value in source_texts:
            ratio = _ratio(label, text_value)
            if ratio > best_ratio:
                best_ratio = ratio
                best_source = text_value
        if best_ratio >= 0.50:
            continue
        result.append({
            'line_index': row.get('line_index'),
            'label': label,
            'line_total': _money(row.get('line_total')),
            'best_source_text': best_source,
            'best_source_similarity': round(best_ratio, 3),
            'reason': 'stored article label has weak support in OCR/parser source lines',
        })
    return result


def _suspected_merged_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in lines:
        label = _line_label(row)
        amounts = _amounts_as_decimal(label)
        score = 0
        reasons = []
        if len(amounts) >= 2:
            score += 4
            reasons.append('multiple_amounts_in_label')
        if re.search(r'\b\d+\s*[xX]\b', label) and len(amounts) >= 1:
            score += 2
            reasons.append('quantity_and_amount_in_label')
        if any(token in label for token in ('==', '»', '"', '‘', '*')):
            score += 1
            reasons.append('ocr_noise_marker')
        if _line_amount(row) >= Decimal('8.00'):
            score += 1
            reasons.append('large_line_total')
        if score <= 0:
            continue
        result.append({
            'line_index': row.get('line_index'),
            'label': label,
            'line_total': _money(row.get('line_total')),
            'amounts_in_label': [float(value) for value in amounts],
            'score': score,
            'reasons': reasons,
        })
    return sorted(result, key=lambda item: (-item['score'], item['line_index'] or 0))


def _suspected_wrong_amount_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in lines:
        label = _line_label(row)
        line_total = _line_amount(row).quantize(Decimal('0.01'))
        unit_price = _to_decimal(row.get('unit_price'))
        amounts = _amounts_as_decimal(label)
        amount_mismatch = [amount for amount in amounts if abs(amount - line_total) > Decimal('0.01')]
        if not amount_mismatch:
            continue
        result.append({
            'line_index': row.get('line_index'),
            'label': label,
            'line_total': float(line_total),
            'unit_price': float(unit_price.quantize(Decimal('0.01'))) if unit_price is not None else None,
            'amounts_in_label': [float(value) for value in amounts],
            'reason': 'amount displayed in label differs from stored line_total',
        })
    return result


def _discount_or_correction_candidates(source_lines: list[dict[str, Any]], stored_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in source_lines:
        text_value = str(item.get('text') or '')
        lowered = text_value.lower()
        if not any(token in lowered for token in ('korting', 'voordeel', 'actie', 'bonus', 'prijsvoordeel', 'statiegeld', 'emballage', 'retour')):
            continue
        result.append({
            **item,
            'amount_candidates': _amount_tokens(text_value),
            'reason': 'source line looks like discount/correction/deposit candidate',
        })
    for row in stored_lines:
        label = _line_label(row)
        lowered = label.lower()
        if _line_discount(row) != 0 or any(token in lowered for token in ('korting', 'voordeel', 'actie', 'bonus', 'prijsvoordeel', 'statiegeld', 'emballage', 'retour')):
            result.append({
                'line_index': row.get('line_index'),
                'text': label,
                'line_total': _money(row.get('line_total')),
                'discount_amount': _money(row.get('discount_amount')),
                'reason': 'stored line has discount/correction/deposit signal',
            })
    return result[:40]


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
            record = _fetch_record(conn, str(actual.get('receipt_table_id')))
            stored_lines = _fetch_lines(conn, str(actual.get('receipt_table_id')))
            parserflow = _run_parserflow(record) if record else {'error': 'record not found'}
            source_lines = parserflow.get('raw_ocr_or_parser_text_lines') or []
            gross = sum((_line_amount(row) for row in stored_lines if not row.get('is_deleted')), Decimal('0')).quantize(Decimal('0.01'))
            line_discount = sum((_line_discount(row) for row in stored_lines if not row.get('is_deleted')), Decimal('0')).quantize(Decimal('0.01'))
            receipt_discount = _to_decimal(actual.get('discount_total')) or Decimal('0')
            net = _to_decimal(actual.get('net_line_sum_used_for_decision')) or (gross + line_discount).quantize(Decimal('0.01'))
            total_amount = _to_decimal(actual.get('total_amount')) or Decimal('0')
            reports.append({
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
                'line_sum_gap_to_total': float((net - total_amount).quantize(Decimal('0.01'))),
                'stored_article_lines': [_summarize_line(row) for row in stored_lines],
                'parserflow': parserflow,
                'amount_bearing_source_lines': _amount_bearing_source_lines(source_lines)[:80],
                'source_lines_not_stored_as_articles': _source_lines_not_stored(source_lines, stored_lines),
                'stored_articles_not_supported_by_source_line': _stored_lines_not_supported(source_lines, stored_lines),
                'suspected_merged_article_lines': _suspected_merged_lines(stored_lines),
                'suspected_wrong_amount_lines': _suspected_wrong_amount_lines(stored_lines),
                'discount_or_correction_candidates': _discount_or_correction_candidates(source_lines, stored_lines),
                'read_only': True,
            })
    return {
        'test': 'R9-38A12b PLUS foto 1/foto 2 read-only parserflow gap analysis',
        'household_id': '1',
        'target_patterns': TARGET_PATTERNS,
        'reports': reports,
        'read_only': True,
        'database_write_intent': False,
    }


def main() -> int:
    print(json.dumps(build_report(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
