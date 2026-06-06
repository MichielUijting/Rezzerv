"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _extract_payload_from_paddle_item,
    _get_paddle_ocr,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
)
from app.receipt_ingestion.service_parts.plus_photo_preprocessed_fallback_ocr import guarded_plus_preprocessed_ocr_fallback
from app.services.receipt_service import _resolve_reparse_source_payload

TARGET_RECEIPT_TABLE_ID = '7323172c2f364be5b53be9e11efb1ef4'
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b8')
OUTPUT_JSON = OUTPUT_ROOT / 'plus_correction_logic_diagnosis.json'
AMOUNT_TOKEN_RE = re.compile(r'[€£CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.IGNORECASE)
SUBTOTAL_TOKENS = ('subtotaal',)
TOTAL_TOKENS = ('totaal',)
CORRECTION_TOKENS = ('zegel', 'actie', 'pluspunten', 'piuspunten')
DISCOUNT_CONTEXT_TOKENS = ('plus geeft', 'voordeel', 'korting')


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _parse_amount_token(token: str) -> Decimal | None:
    raw = _norm(token).upper().replace('EUR', '').replace('€', '').replace('£', '').strip()
    sign = Decimal('-1') if raw.startswith('C-') or raw.startswith('E-') or raw.startswith('-') else Decimal('1')
    raw = raw.replace('C-', '').replace('E-', '').replace('C', '').replace('E', '').replace('-', '').replace(',', '.')
    try:
        return (Decimal(raw) * sign).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _amounts_from_line(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for token in AMOUNT_TOKEN_RE.findall(line or ''):
        value = _parse_amount_token(token)
        if value is not None:
            values.append(value)
    return values


def _is_pluspunten_line(lowered: str) -> bool:
    return 'pluspunten' in lowered or 'piuspunten' in lowered


def _classify_correction_b8(line: str) -> tuple[str, Decimal | None, str]:
    lowered = line.lower()
    amounts = _amounts_from_line(line)
    if not any(token in lowered for token in CORRECTION_TOKENS):
        return 'non_correction', None, 'line_between_subtotal_and_total_but_no_correction_keyword'
    if _is_pluspunten_line(lowered):
        amount = amounts[-1] if amounts else None
        if amount is not None and amount < 0:
            amount = abs(amount)
        return 'pluspunten_credit', amount, 'PLUSPunten takes precedence over ZEGEL; amount stays positive even when the line also contains ZEGEL'
    if 'zegel' in lowered or 'actie' in lowered:
        amount = amounts[-1] if amounts else None
        if amount is not None and amount > 0:
            amount = -amount
            return 'subtotal_discount', amount, 'ZEGEL/ACTIE line: positive OCR amount interpreted as negative receipt-level correction'
        return 'subtotal_discount', amount, 'ZEGEL/ACTIE line: signed amount treated as receipt-level correction'
    return 'unknown_correction', amounts[-1] if amounts else None, 'fallback correction classification'


def _find_subtotal_total_window(lines: list[str]) -> tuple[int | None, int | None, list[str]]:
    subtotal_index = None
    for idx, line in enumerate(lines):
        if any(token in line.lower() for token in SUBTOTAL_TOKENS):
            subtotal_index = idx
            break
    if subtotal_index is None:
        return None, None, []
    total_index = None
    for idx in range(subtotal_index + 1, len(lines)):
        if any(token in lines[idx].lower() for token in TOTAL_TOKENS):
            total_index = idx
            break
    if total_index is None:
        return subtotal_index, None, []
    return subtotal_index, total_index, lines[subtotal_index + 1:total_index]


def _extract_texts_scores_boxes(result: Any) -> tuple[list[str], list[float], list[Any]]:
    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        current_scores = _normalize_paddle_collection(payload.get('rec_scores') or payload.get('scores'))
        current_boxes = payload.get('rec_boxes')
        if current_boxes is None:
            current_boxes = payload.get('dt_polys')
        if current_boxes is None:
            current_boxes = payload.get('rec_polys')
        current_boxes = _normalize_paddle_collection(current_boxes)
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        for score in current_scores:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        boxes.extend(current_boxes[: len(normalized_texts)])
    return texts, scores, boxes


def _fetch_target() -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(text('''
            SELECT rr.id AS raw_receipt_id, rr.original_filename, rr.mime_type,
                   rr.storage_path, rt.id AS receipt_table_id, rt.total_amount,
                   rt.line_count, rem.body_html, rem.body_text, rem.selected_part_type
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
            WHERE rt.deleted_at IS NULL AND rt.id = :receipt_table_id
            LIMIT 1
        '''), {'receipt_table_id': TARGET_RECEIPT_TABLE_ID}).mappings().first()
    if row is None:
        raise RuntimeError(f'Active receipt_table_id not found: {TARGET_RECEIPT_TABLE_ID}')
    return dict(row)


def _stored_rows(receipt_table_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT line_index, raw_label, normalized_label, line_total,
                   discount_amount, unit_price, quantity
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
            ORDER BY line_index, id
        '''), {'receipt_table_id': receipt_table_id}).mappings().all()
    return [dict(row) for row in rows]


def _ocr_lines(file_bytes: bytes, filename: str) -> tuple[list[str], list[str], dict[str, Any]]:
    model = _get_paddle_ocr()
    if model is None:
        raise RuntimeError('PaddleOCR model is not available')
    suffix = Path(filename).suffix.lower() or '.jpg'
    with tempfile.TemporaryDirectory(prefix='rezzerv-r9-38b8-') as temp_dir:
        image_path = Path(temp_dir) / f'image{suffix}'
        image_path.write_bytes(file_bytes)
        raw_result = model.predict(str(image_path))
    texts, _scores, boxes = _extract_texts_scores_boxes(raw_result)
    current_lines = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    preprocessed = guarded_plus_preprocessed_ocr_fallback(
        model=model,
        file_bytes=file_bytes,
        filename=filename,
        runtime_texts=texts,
        runtime_boxes=boxes,
        runtime_lines=current_lines,
    )
    fallback_lines = preprocessed.get('fallback_lines') or []
    return current_lines, list(fallback_lines), preprocessed


def _line_sums(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gross = sum((_money(row.get('line_total')) for row in rows), Decimal('0.00'))
    stored_line_discounts = sum((_money(row.get('discount_amount')) for row in rows), Decimal('0.00'))
    return {
        'stored_article_gross_sum': _to_float(gross),
        'stored_line_discount_sum': _to_float(stored_line_discounts),
        'stored_article_net_sum': _to_float(gross + stored_line_discounts),
    }


def _find_missing_line_discounts(fallback_lines: list[str], stored_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    previous_article_line: str | None = None
    previous_article_label: str | None = None
    stored_labels = [str(row.get('raw_label') or '').lower() for row in stored_rows]
    stored_discounts_by_label = {str(row.get('raw_label') or '').lower(): _money(row.get('discount_amount')) for row in stored_rows}
    for line in fallback_lines:
        lowered = line.lower()
        amounts = _amounts_from_line(line)
        if any(token in lowered for token in DISCOUNT_CONTEXT_TOKENS) and amounts:
            amount = amounts[-1]
            matched_label = None
            if previous_article_label:
                for stored_label in stored_labels:
                    if previous_article_label.lower() in stored_label or stored_label in previous_article_label.lower():
                        matched_label = stored_label
                        break
            stored_discount = stored_discounts_by_label.get(matched_label or '', Decimal('0.00'))
            evidence.append({
                'discount_line': line,
                'discount_amount': _to_float(amount),
                'attached_to_previous_article_line': previous_article_line,
                'matched_stored_label': matched_label,
                'stored_discount_currently': _to_float(stored_discount),
                'is_missing_in_stored_db': stored_discount == Decimal('0.00'),
                'evidence_reason': 'PLUS geeft/voordeel discount line attaches to the immediately preceding article line in fallback OCR order',
            })
            continue
        if amounts and not any(token in lowered for token in ('subtotaal', 'totaal')) and not any(token in lowered for token in CORRECTION_TOKENS):
            label = re.sub(AMOUNT_TOKEN_RE, '', line).strip()
            if label and not any(token in label.lower() for token in DISCOUNT_CONTEXT_TOKENS):
                previous_article_line = line
                previous_article_label = label
    return evidence


def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    target = _fetch_target()
    filename = str(target.get('original_filename') or '')
    file_bytes = Path(str(target.get('storage_path'))).read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(target, file_bytes)
    runtime_lines, fallback_lines, preprocessed_diag = _ocr_lines(parse_bytes, parse_filename or filename)
    analysis_lines = fallback_lines or runtime_lines
    subtotal_index, total_index, correction_window = _find_subtotal_total_window(analysis_lines)
    stored_rows = _stored_rows(str(target.get('receipt_table_id')))
    line_discount_evidence = _find_missing_line_discounts(fallback_lines, stored_rows)
    stored_sums = _line_sums(stored_rows)
    stored_gross = Decimal(str(stored_sums['stored_article_gross_sum'])).quantize(Decimal('0.01'))
    stored_line_discount = Decimal(str(stored_sums['stored_line_discount_sum'])).quantize(Decimal('0.01'))
    missing_line_discount_sum = sum((_money(row.get('discount_amount')) for row in line_discount_evidence if row.get('is_missing_in_stored_db')), Decimal('0.00'))
    corrected_line_discount = stored_line_discount + missing_line_discount_sum
    corrected_article_net = stored_gross + corrected_line_discount
    correction_rows = []
    correction_total = Decimal('0.00')
    for offset, line in enumerate(correction_window):
        classification, amount, reason = _classify_correction_b8(line)
        included = classification in {'pluspunten_credit', 'subtotal_discount', 'unknown_correction'} and amount is not None
        row = {
            'window_index': offset,
            'line': line,
            'classification': classification,
            'amount': _to_float(amount),
            'included_in_receipt_level_correction_sum': included,
            'reason': reason,
        }
        correction_rows.append(row)
        if included:
            correction_total += amount or Decimal('0.00')
    total_amount = _money(target.get('total_amount'))
    predicted = corrected_article_net + correction_total
    result = {
        'test': 'R9-38B8 PLUS correction logic diagnosis',
        'read_only': True,
        'database_write_intent': False,
        'parser_invoked': False,
        'runtime_behavior_changed': False,
        'target': {
            'receipt_table_id': target.get('receipt_table_id'),
            'raw_receipt_id': target.get('raw_receipt_id'),
            'original_filename': filename,
            'parse_filename': parse_filename,
            'parse_mime_type': parse_mime_type,
            'stored_total_amount': target.get('total_amount'),
            'stored_line_count': target.get('line_count'),
        },
        'line_source_used_for_analysis': 'fallback_lines' if fallback_lines else 'runtime_lines',
        'fallback_lines': fallback_lines,
        'subtotal_total_window': {
            'subtotal_index': subtotal_index,
            'total_index': total_index,
            'lines_between_subtotal_and_total': correction_window,
        },
        'preprocessed_fallback_summary': {
            'preprocessed_attempted': preprocessed_diag.get('preprocessed_attempted'),
            'preprocessed_applied': bool(preprocessed_diag.get('fallback_lines')),
            'runtime_reject_reason': (preprocessed_diag.get('runtime_diagnostics') or {}).get('fallback_reject_reason'),
            'preprocessed_reject_reason': ((preprocessed_diag.get('preprocessed_diagnostics') or {}).get('fallback_reject_reason') if preprocessed_diag.get('preprocessed_diagnostics') else None),
        },
        'stored_db_lines_for_comparison_only': stored_rows,
        'stored_line_sums': stored_sums,
        'line_discount_evidence': line_discount_evidence,
        'missing_line_discount_sum': _to_float(missing_line_discount_sum),
        'corrected_line_discount_sum': _to_float(corrected_line_discount),
        'corrected_article_net_sum': _to_float(corrected_article_net),
        'receipt_level_correction_candidates': correction_rows,
        'receipt_level_correction_sum': _to_float(correction_total),
        'predicted_total_after_b8_corrections': _to_float(predicted),
        'stored_total_amount': _to_float(total_amount),
        'matches_total_after_b8_corrections': predicted == total_amount,
        'delta_after_b8_corrections': _to_float(total_amount - predicted),
        'expected_acceptance_calculation': {
            'article_gross': _to_float(stored_gross),
            'line_discount_bami_and_existing': _to_float(stored_line_discount),
            'line_discount_cashew_missing_evidence': _to_float(missing_line_discount_sum),
            'receipt_level_corrections': _to_float(correction_total),
            'predicted_total': _to_float(predicted),
            'expected_total': _to_float(total_amount),
            'delta': _to_float(total_amount - predicted),
        },
        'runtime_seconds': round(time.perf_counter() - started, 3),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['output_json_path'] = str(OUTPUT_JSON)
    return result


def main() -> int:
    report = build_report()
    summary = {
        'test': report['test'],
        'status': 'ok',
        'output_json_path': report['output_json_path'],
        'runtime_seconds': report['runtime_seconds'],
        'expected_acceptance_calculation': report['expected_acceptance_calculation'],
        'matches_total_after_b8_corrections': report['matches_total_after_b8_corrections'],
        'line_discount_evidence': report['line_discount_evidence'],
        'receipt_level_correction_candidates': report['receipt_level_correction_candidates'],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
