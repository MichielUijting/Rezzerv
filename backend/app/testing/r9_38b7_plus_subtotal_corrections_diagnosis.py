from __future__ import annotations

import io
import json
import re
import tempfile
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
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
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b7')
OUTPUT_JSON = OUTPUT_ROOT / 'plus_subtotal_corrections_diagnosis.json'
AMOUNT_TOKEN_RE = re.compile(r'[€£CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.IGNORECASE)
SUBTOTAL_TOKENS = ('subtotaal',)
TOTAL_TOKENS = ('totaal',)
CORRECTION_TOKENS = ('zegel', 'actie', 'pluspunten')


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _to_float(value: Decimal) -> float:
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


def _classify_correction(line: str) -> tuple[str, Decimal | None, str]:
    lowered = line.lower()
    amounts = _amounts_from_line(line)
    if not any(token in lowered for token in CORRECTION_TOKENS):
        return 'non_correction', None, 'line_between_subtotal_and_total_but_no_correction_keyword'
    if 'pluspunten' in lowered:
        amount = amounts[-1] if amounts else None
        return 'pluspunten_credit', amount, 'PLUSPunten line: last amount is treated as positive credit/debit as OCR sign indicates'
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
        lowered = line.lower()
        if any(token in lowered for token in SUBTOTAL_TOKENS):
            subtotal_index = idx
            break
    if subtotal_index is None:
        return None, None, []
    total_index = None
    for idx in range(subtotal_index + 1, len(lines)):
        lowered = lines[idx].lower()
        if any(token in lowered for token in TOTAL_TOKENS):
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
    with tempfile.TemporaryDirectory(prefix='rezzerv-r9-38b7-') as temp_dir:
        image_path = Path(temp_dir) / f'image{suffix}'
        image_path.write_bytes(file_bytes)
        raw_result = model.predict(str(image_path))
    texts, scores, boxes = _extract_texts_scores_boxes(raw_result)
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
    line_discounts = sum((_money(row.get('discount_amount')) for row in rows), Decimal('0.00'))
    net = gross + line_discounts
    return {
        'stored_article_gross_sum': _to_float(gross),
        'stored_line_discount_sum': _to_float(line_discounts),
        'stored_article_net_sum': _to_float(net),
    }


def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    target = _fetch_target()
    filename = str(target.get('original_filename') or '')
    file_bytes = Path(str(target.get('storage_path'))).read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(target, file_bytes)
    runtime_lines, fallback_lines, preprocessed_diag = _ocr_lines(parse_bytes, parse_filename or filename)
    analysis_lines = fallback_lines or runtime_lines
    subtotal_index, total_index, correction_window = _find_subtotal_total_window(analysis_lines)
    correction_rows = []
    correction_total = Decimal('0.00')
    for offset, line in enumerate(correction_window):
        classification, amount, reason = _classify_correction(line)
        row = {
            'window_index': offset,
            'line': line,
            'classification': classification,
            'amount': _to_float(amount) if amount is not None else None,
            'included_in_receipt_level_correction_sum': classification in {'pluspunten_credit', 'subtotal_discount', 'unknown_correction'} and amount is not None,
            'reason': reason,
        }
        correction_rows.append(row)
        if row['included_in_receipt_level_correction_sum']:
            correction_total += amount or Decimal('0.00')
    stored_rows = _stored_rows(str(target.get('receipt_table_id')))
    sums = _line_sums(stored_rows)
    stored_net = Decimal(str(sums['stored_article_net_sum'])).quantize(Decimal('0.01'))
    total_amount = _money(target.get('total_amount'))
    predicted = stored_net + correction_total
    missing = total_amount - stored_net
    result = {
        'test': 'R9-38B7 PLUS subtotal corrections diagnosis',
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
        'line_source_used_for_correction_window': 'fallback_lines' if fallback_lines else 'runtime_lines',
        'runtime_lines': runtime_lines,
        'fallback_lines': fallback_lines,
        'preprocessed_fallback_summary': {
            'preprocessed_attempted': preprocessed_diag.get('preprocessed_attempted'),
            'preprocessed_applied': bool(preprocessed_diag.get('fallback_lines')),
            'runtime_reject_reason': (preprocessed_diag.get('runtime_diagnostics') or {}).get('fallback_reject_reason'),
            'preprocessed_reject_reason': ((preprocessed_diag.get('preprocessed_diagnostics') or {}).get('fallback_reject_reason') if preprocessed_diag.get('preprocessed_diagnostics') else None),
        },
        'subtotal_total_window': {
            'subtotal_index': subtotal_index,
            'total_index': total_index,
            'lines_between_subtotal_and_total': correction_window,
        },
        'stored_db_lines_for_comparison_only': stored_rows,
        'stored_line_sums': sums,
        'receipt_level_correction_candidates': correction_rows,
        'receipt_level_correction_sum': _to_float(correction_total),
        'missing_correction_to_match_total': _to_float(missing),
        'predicted_total_after_receipt_level_corrections': _to_float(predicted),
        'stored_total_amount': _to_float(total_amount),
        'matches_total_after_corrections': predicted == total_amount,
        'delta_after_corrections': _to_float(total_amount - predicted),
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
        'line_source_used_for_correction_window': report['line_source_used_for_correction_window'],
        'stored_line_sums': report['stored_line_sums'],
        'receipt_level_correction_sum': report['receipt_level_correction_sum'],
        'missing_correction_to_match_total': report['missing_correction_to_match_total'],
        'predicted_total_after_receipt_level_corrections': report['predicted_total_after_receipt_level_corrections'],
        'stored_total_amount': report['stored_total_amount'],
        'matches_total_after_corrections': report['matches_total_after_corrections'],
        'delta_after_corrections': report['delta_after_corrections'],
        'receipt_level_correction_candidates': report['receipt_level_correction_candidates'],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
