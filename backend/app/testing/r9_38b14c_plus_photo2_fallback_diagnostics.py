from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _extract_payload_from_paddle_item,
    _get_paddle_ocr,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
)
from app.receipt_ingestion.service_parts.plus_photo_line_grouping_fallback import diagnose_plus_photo_line_grouping_fallback
from app.services.receipt_service import _resolve_reparse_source_payload

TARGET_RECEIPT_TABLE_ID = '4ebdf7bf8a344093b6232ec5dd05b3c9'
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b14c')
OUTPUT_JSON = OUTPUT_ROOT / 'plus_photo2_fallback_runtime_diagnostics.json'


def _payload_boxes(payload):
    boxes = payload.get('rec_boxes')
    if boxes is None:
        boxes = payload.get('dt_polys')
    if boxes is None:
        boxes = payload.get('rec_polys')
    return boxes


def _extract_texts_and_boxes(result):
    texts = []
    boxes = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = [str(x) for x in _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts')) if str(x).strip()]
        current_boxes = _normalize_paddle_collection(_payload_boxes(payload))
        texts.extend(current_texts)
        boxes.extend(current_boxes[: len(current_texts)])
    return texts, boxes[: len(texts)]


def _target_record():
    with engine.connect() as conn:
        row = conn.execute(text('''
            SELECT rr.original_filename, rr.storage_path, rem.body_html, rem.body_text, rem.selected_part_type
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
            WHERE rt.id = :rid
            LIMIT 1
        '''), {'rid': TARGET_RECEIPT_TABLE_ID}).mappings().first()
    if row is None:
        raise RuntimeError(f'Receipt not found: {TARGET_RECEIPT_TABLE_ID}')
    return dict(row)


def build_report():
    started = time.perf_counter()
    record = _target_record()
    raw = Path(record['storage_path']).read_bytes()
    parse_bytes, parse_filename, parse_mime = _resolve_reparse_source_payload(record, raw)

    suffix = Path(parse_filename or record['original_filename']).suffix.lower() or '.jpg'
    with tempfile.TemporaryDirectory(prefix='r9-38b14c-') as temp_dir:
        image_path = Path(temp_dir) / ('image' + suffix)
        image_path.write_bytes(parse_bytes)
        result = _get_paddle_ocr().predict(str(image_path))

    texts, boxes = _extract_texts_and_boxes(result)
    current_lines = _group_paddle_texts_to_lines(texts, boxes)
    diagnostics = diagnose_plus_photo_line_grouping_fallback(
        filename=parse_filename or record['original_filename'],
        texts=texts,
        boxes=boxes,
        current_lines=current_lines,
    )

    report = {
        'test': 'R9-38B14c PLUS photo 2 fallback runtime diagnostics',
        'read_only': True,
        'database_write_intent': False,
        'parser_write_intent': False,
        'target': {
            'receipt_table_id': TARGET_RECEIPT_TABLE_ID,
            'original_filename': record['original_filename'],
            'parse_filename': parse_filename,
            'parse_mime': parse_mime,
        },
        'current_lines': current_lines,
        'diagnostics': diagnostics,
        'summary': {
            'has_suspicious_article_merges': diagnostics.get('has_suspicious_article_merges'),
            'has_pluspunten_correction': diagnostics.get('has_pluspunten_correction'),
            'article_block_detected': diagnostics.get('article_block_detected'),
            'article_block_fragment_count': diagnostics.get('article_block_fragment_count'),
            'reconstruction_valid': diagnostics.get('reconstruction_valid'),
            'replacement_valid': diagnostics.get('replacement_valid'),
            'fallback_applied': diagnostics.get('fallback_applied'),
            'fallback_reject_reason': diagnostics.get('fallback_reject_reason'),
            'applied_pairing_mode': diagnostics.get('applied_pairing_mode'),
            'reconstructed_article_lines': diagnostics.get('reconstructed_article_lines'),
            'final_lines_after_fallback': diagnostics.get('final_lines_after_fallback'),
        },
        'runtime_seconds': round(time.perf_counter() - started, 3),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    report['output_json_path'] = str(OUTPUT_JSON)
    return report


def main():
    report = build_report()
    print(json.dumps({
        'status': 'ok',
        'output_json_path': report['output_json_path'],
        'runtime_seconds': report['runtime_seconds'],
        **report['summary'],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
