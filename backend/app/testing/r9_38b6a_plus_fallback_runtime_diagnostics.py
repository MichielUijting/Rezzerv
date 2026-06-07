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

import io
import json
import tempfile
import time
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
from app.receipt_ingestion.service_parts.plus_photo_line_grouping_fallback import diagnose_plus_photo_line_grouping_fallback
from app.services.receipt_service import _resolve_reparse_source_payload

TARGET_RECEIPT_TABLE_ID = '7323172c2f364be5b53be9e11efb1ef4'
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b6a')
OUTPUT_JSON = OUTPUT_ROOT / 'plus_fallback_runtime_diagnostics.json'


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


def _db_rows(receipt_table_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT line_index, raw_label, normalized_label, line_total,
                   discount_amount, unit_price, quantity
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
            ORDER BY line_index, id
        '''), {'receipt_table_id': receipt_table_id}).mappings().all()
    return [dict(row) for row in rows]


def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    record = _fetch_target()
    filename = str(record.get('original_filename') or '')
    file_bytes = Path(str(record.get('storage_path'))).read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(record, file_bytes)

    model = _get_paddle_ocr()
    if model is None:
        raise RuntimeError('PaddleOCR model is not available')
    with tempfile.TemporaryDirectory(prefix='rezzerv-r9-38b6a-') as temp_dir:
        suffix = Path(parse_filename or filename).suffix.lower() or '.jpg'
        image_path = Path(temp_dir) / f'image{suffix}'
        image_path.write_bytes(parse_bytes)
        raw_result = model.predict(str(image_path))
    texts, scores, boxes = _extract_texts_scores_boxes(raw_result)
    current_lines = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    diagnostics = diagnose_plus_photo_line_grouping_fallback(
        filename=parse_filename or filename,
        texts=texts,
        boxes=boxes,
        current_lines=current_lines,
    )
    result = {
        'test': 'R9-38B6a PLUS fallback runtime diagnostics',
        'read_only': True,
        'database_write_intent': False,
        'parser_invoked': False,
        'runtime_behavior_changed': False,
        'target': {
            'receipt_table_id': record.get('receipt_table_id'),
            'raw_receipt_id': record.get('raw_receipt_id'),
            'original_filename': filename,
            'parse_filename': parse_filename,
            'parse_mime_type': parse_mime_type,
            'stored_total_amount': record.get('total_amount'),
            'stored_line_count': record.get('line_count'),
        },
        'ocr_fragment_count': len(texts),
        'ocr_box_count': len(boxes),
        'ocr_confidence_average': round(sum(scores) / len(scores), 4) if scores else None,
        'fallback_diagnostics': diagnostics,
        'stored_db_lines_for_comparison_only': _db_rows(str(record.get('receipt_table_id'))),
        'runtime_seconds': round(time.perf_counter() - started, 3),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['output_json_path'] = str(OUTPUT_JSON)
    return result


def main() -> int:
    report = build_report()
    diag = report.get('fallback_diagnostics') or {}
    summary = {
        'test': report['test'],
        'status': 'ok',
        'output_json_path': report['output_json_path'],
        'runtime_seconds': report['runtime_seconds'],
        'guardrails': {
            'is_image_receipt': diag.get('is_image_receipt'),
            'has_texts': diag.get('has_texts'),
            'has_boxes': diag.get('has_boxes'),
            'texts_boxes_same_length': diag.get('texts_boxes_same_length'),
            'looks_like_plus_receipt': diag.get('looks_like_plus_receipt'),
            'has_suspicious_article_merges': diag.get('has_suspicious_article_merges'),
            'article_block_detected': diag.get('article_block_detected'),
            'reconstruction_valid': diag.get('reconstruction_valid'),
            'replacement_valid': diag.get('replacement_valid'),
            'fallback_applied': diag.get('fallback_applied'),
            'fallback_reject_reason': diag.get('fallback_reject_reason'),
        },
        'current_line_count': len(diag.get('current_lines_before_fallback') or []),
        'reconstructed_line_count': len(diag.get('reconstructed_article_lines') or []),
        'final_line_count': len(diag.get('final_lines_after_fallback') or []),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
