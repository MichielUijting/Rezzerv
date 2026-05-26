from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Response
from sqlalchemy import text

from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline
from app.services.receipt_service import (
    _convert_webp_to_png_bytes,
    _extract_pdf_text,
    _extract_text_from_eml,
    _html_to_text,
    _normalize_text_lines,
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
    _ocr_pdf_text_with_ocrmypdf,
    _preprocess_pdf_text,
    apply_receipt_image_preprocessing,
)


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _elapsed_ms(start_ms: float) -> int:
    return int(round(_now_ms() - start_ms))


def _to_number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if abs(number - int(number)) < 0.000001:
        return int(number)
    return round(number, 4)


def _normalize_filename(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())


def _safe_excerpt(value: str | None, max_chars: int = 12000) -> str:
    text_value = str(value or '')
    return text_value[:max_chars]




AMOUNT_LINE_PATTERN = re.compile(
    # ASCII-only on purpose: OCR/report scripts have shown currency symbols can be mojibaked.
    # This layer only detects amount-bearing lines; store-specific interpretation comes later.
    r'(?<![A-Za-z0-9])(?:EUR|EURO|E|C)?\s*-?\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)
COMPACT_AMOUNT_LINE_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])\d+\s*[xX]\s*\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)


def _normalize_ocr_amount_token(value: str | None) -> str:
    token = re.sub(r'\s+', '', str(value or '').strip())
    token = re.sub(r'^(?:EUR|EURO|E|C)', '', token, flags=re.IGNORECASE)
    return token


def _extract_ocr_amounts(line: str | None) -> list[str]:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    amounts = [_normalize_ocr_amount_token(match.group(0)) for match in AMOUNT_LINE_PATTERN.finditer(normalized)]
    return [amount for amount in amounts if amount]


def _build_amount_line_candidates(engine_name: str, raw_lines: list[str] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if not normalized:
            continue
        amounts = _extract_ocr_amounts(normalized)
        compact_match = bool(COMPACT_AMOUNT_LINE_PATTERN.search(normalized))
        if not amounts and not compact_match:
            continue
        candidates.append({
            'source_engine': engine_name,
            'source_line_index': index,
            'raw_line': raw_line,
            'normalized_line': normalized,
            'amounts_detected': amounts,
            'last_amount': amounts[-1] if amounts else None,
            'candidate_type_unclassified': True,
            'classification_applied': False,
            'store_filtering_applied': False,
            'reason': 'amount_pattern_detected_before_store_filtering',
        })
    return candidates


def _ocr_amount_line_candidate_summary(paddle_lines: list[str] | None, tesseract_lines: list[str] | None) -> dict[str, Any]:
    paddle_candidates = _build_amount_line_candidates('paddle', paddle_lines)
    tesseract_candidates = _build_amount_line_candidates('tesseract', tesseract_lines)
    all_candidates = paddle_candidates + tesseract_candidates
    return {
        'count': len(all_candidates),
        'paddle_count': len(paddle_candidates),
        'tesseract_count': len(tesseract_candidates),
        'candidates': all_candidates,
        'truncated': False,
        'scope': 'image_ocr_amount_lines_before_parser_and_store_filtering',
    }

def _line_summary(lines: list[str]) -> dict[str, Any]:
    return {
        'count': len(lines or []),
        'lines': list(lines or [])[:500],
        'truncated': len(lines or []) > 500,
    }


def _receipt_line_dict(row: dict[str, Any]) -> dict[str, Any]:
    label = row.get('corrected_raw_label') or row.get('raw_label') or row.get('normalized_label')
    return {
        'line_number': int(row.get('line_index') or 0) + 1,
        'raw_label': row.get('raw_label'),
        'normalized_label': row.get('normalized_label'),
        'corrected_raw_label': row.get('corrected_raw_label'),
        'article_name': label,
        'quantity': _to_number(row.get('corrected_quantity') if row.get('corrected_quantity') is not None else row.get('quantity')),
        'unit': row.get('corrected_unit') or row.get('unit'),
        'unit_price': _to_number(row.get('corrected_unit_price') if row.get('corrected_unit_price') is not None else row.get('unit_price')),
        'line_total': _to_number(row.get('corrected_line_total') if row.get('corrected_line_total') is not None else row.get('line_total')),
        'discount_amount': _to_number(row.get('discount_amount')),
        'barcode': row.get('barcode'),
        'confidence_score': _to_number(row.get('confidence_score')),
        'source_index': row.get('source_index') if 'source_index' in row else None,
        'is_deleted': bool(row.get('is_deleted') or 0),
        'is_validated': bool(row.get('is_validated') or 0),
    }


def _baseline_detail_map(conn, household_id: str | None = None) -> dict[str, dict[str, Any]]:
    validation = validate_receipt_status_baseline(conn, household_id=household_id)
    result: dict[str, dict[str, Any]] = {}
    for detail in validation.get('details', []) or []:
        key = _normalize_filename(detail.get('matched_original_filename') or detail.get('source_file'))
        if key:
            result[key] = detail
        source_key = _normalize_filename(detail.get('source_file'))
        if source_key:
            result[source_key] = detail
    return result


def _active_receipt_rows(conn, household_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text('''
            SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rr.original_filename,
                   rr.mime_type, rr.storage_path, rt.household_id, rt.store_name,
                   rt.store_chain, rt.total_amount, rt.discount_total, rt.line_count,
                   rt.deleted_at, rr.deleted_at AS raw_deleted_at
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE rt.household_id = :household_id
              AND rt.deleted_at IS NULL
              AND rr.deleted_at IS NULL
            ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
        '''),
        {'household_id': str(household_id)},
    ).mappings().all()
    return [dict(row) for row in rows]


def build_receipt_line_diagnosis(
    engine,
    household_id: str = '1',
    filenames: list[str] | None = None,
) -> dict[str, Any]:
    start_total = _now_ms()
    per_receipt_perf: list[dict[str, Any]] = []
    with engine.begin() as conn:
        baseline_map = _baseline_detail_map(conn, household_id=str(household_id) if household_id is not None else None)
        line_columns = {str(row.get('name')) for row in conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings().all()}
        source_index_select = ', rtl.source_index' if 'source_index' in line_columns else ''
        receipt_rows = _active_receipt_rows(conn, str(household_id))

        receipts: list[dict[str, Any]] = []
        for row_dict in receipt_rows:
            receipt_start = _now_ms()
            receipt_id = str(row_dict.get('receipt_table_id'))
            line_rows = conn.execute(
                text(f'''
                    SELECT rtl.id, rtl.receipt_table_id, rtl.line_index, rtl.raw_label,
                           rtl.normalized_label, rtl.corrected_raw_label, rtl.quantity,
                           rtl.corrected_quantity, rtl.unit, rtl.corrected_unit, rtl.unit_price,
                           rtl.corrected_unit_price, rtl.line_total, rtl.corrected_line_total,
                           rtl.discount_amount, rtl.barcode, rtl.confidence_score,
                           rtl.is_deleted, rtl.is_validated {source_index_select}
                    FROM receipt_table_lines rtl
                    WHERE rtl.receipt_table_id = :receipt_table_id
                    ORDER BY rtl.line_index, rtl.id
                '''),
                {'receipt_table_id': receipt_id},
            ).mappings().all()
            accepted_lines = [_receipt_line_dict(dict(line)) for line in line_rows if not line.get('is_deleted')]
            baseline = baseline_map.get(_normalize_filename(row_dict.get('original_filename')), {})
            failed_criteria = baseline.get('failed_criteria') or []
            receipts.append({
                'filename': row_dict.get('original_filename'),
                'receipt_table_id': receipt_id,
                'store_name': row_dict.get('store_name'),
                'store_chain': row_dict.get('store_chain'),
                'po_norm_status_label': baseline.get('po_norm_status_label'),
                'expected_line_count': baseline.get('expected_line_count'),
                'actual_line_count': len(accepted_lines),
                'reported_line_count': _to_number(row_dict.get('line_count')),
                'total_amount': _to_number(row_dict.get('total_amount')),
                'discount_total': _to_number(row_dict.get('discount_total')),
                'sum_line_total_used_for_decision': baseline.get('sum_line_total_used_for_decision'),
                'net_line_sum_used_for_decision': baseline.get('net_line_sum_used_for_decision'),
                'failed_criteria': failed_criteria,
                'stored_accepted_lines': accepted_lines,
                'diagnosis_only': True,
                'live_reparse_from_source': {
                    'available': False,
                    'skipped': True,
                    'reason': 'disabled_by_R9_31F_1_stable_swagger_report',
                },
            })
            per_receipt_perf.append({
                'filename': row_dict.get('original_filename'),
                'receipt_table_id': receipt_id,
                'duration_ms': _elapsed_ms(receipt_start),
                'live_reparse_executed': False,
                'live_reparse_duration_ms': 0,
                'storage_read_duration_ms': 0,
                'parse_duration_ms': 0,
            })

    total_duration = _elapsed_ms(start_total)
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only stored line-level diagnose; gebruikt alle actieve kassabonnen.',
        'scope': {
            'read_only': True,
            'active_receipts_only': True,
            'parser_changed': False,
            'status_classification_changed': False,
            'ui_changed': False,
            'target_filenames': [],
            'selection': 'all_active_receipts',
            'status_source': 'receipt_status_baseline_service_v4.py via po_norm_status_label',
            'report_mode': 'stored_only_stable_swagger',
            'includeLiveReparse': False,
            'includeRawParserInput': False,
            'onlyFailed': False,
            'limit': None,
        },
        'summary': {'requested': 'all_active_receipts', 'returned': len(receipts)},
        'performance': {
            'total_duration_ms': total_duration,
            'receipt_count': len(receipts),
            'live_reparse_count': 0,
            'raw_parser_input_count': 0,
            'per_receipt': per_receipt_perf,
        },
        'receipts': receipts,
    }


def _extract_source_text_for_receipt(row: dict[str, Any]) -> dict[str, Any]:
    start = _now_ms()
    filename = str(row.get('original_filename') or 'receipt')
    mime_type = str(row.get('mime_type') or '')
    suffix = Path(filename).suffix.lower()
    storage_path = Path(str(row.get('storage_path') or ''))
    base_payload: dict[str, Any] = {
        'filename': filename,
        'receipt_table_id': row.get('receipt_table_id'),
        'raw_receipt_id': row.get('raw_receipt_id'),
        'mime_type': mime_type,
        'storage_exists': storage_path.exists(),
        'source_text_stage': 'created_before_parser_preprocessing',
        'parser_changed': False,
        'status_classification_changed': False,
        'database_changed': False,
    }
    if not storage_path.exists():
        return {**base_payload, 'error': 'storage_file_missing', 'duration_ms': _elapsed_ms(start)}

    file_bytes = storage_path.read_bytes()
    try:
        if mime_type == 'application/pdf' or suffix == '.pdf':
            direct_text = _extract_pdf_text(file_bytes)
            direct_lines = _normalize_text_lines(direct_text)
            ocr_text = ''
            ocr_lines: list[str] = []
            if not direct_lines:
                ocr_text = _ocr_pdf_text_with_ocrmypdf(file_bytes, filename)
                ocr_lines = _normalize_text_lines(ocr_text)
            return {
                **base_payload,
                'source_kind': 'pdf',
                'direct_pdf_text': {
                    'available': bool(direct_text.strip()),
                    'char_count': len(direct_text),
                    'excerpt': _safe_excerpt(direct_text),
                    'raw_lines': _line_summary(direct_lines),
                },
                'ocrmypdf_text': {
                    'executed': not bool(direct_lines),
                    'available': bool(ocr_text.strip()),
                    'char_count': len(ocr_text),
                    'excerpt': _safe_excerpt(ocr_text),
                    'raw_lines': _line_summary(ocr_lines),
                },
                'preprocess_not_applied_here': True,
                'duration_ms': _elapsed_ms(start),
            }

        if suffix == '.webp':
            file_bytes = _convert_webp_to_png_bytes(file_bytes)
            filename = f'{Path(filename).stem}.png'
            mime_type = 'image/png'
            suffix = '.png'

        if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
            ocr_file_bytes = file_bytes
            ocr_filename = filename
            preprocessing: dict[str, Any] = {'executed': False}
            try:
                processed_bytes, safe_rotation_decision = apply_receipt_image_preprocessing(file_bytes, filename)
                preprocessing = {
                    'executed': True,
                    'selected_route': getattr(safe_rotation_decision, 'selected_route', None),
                    'reason': getattr(safe_rotation_decision, 'reason', None),
                }
                if processed_bytes != file_bytes:
                    ocr_file_bytes = processed_bytes
                    ocr_filename = f'{Path(filename).stem}-safe-rotation.png'
            except Exception as exc:
                preprocessing = {'executed': True, 'error': f'{exc.__class__.__name__}: {exc}'}
            paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(ocr_file_bytes, ocr_filename)
            tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(ocr_file_bytes, ocr_filename)
            amount_line_candidates = _ocr_amount_line_candidate_summary(paddle_lines, tesseract_lines)
            return {
                **base_payload,
                'source_kind': 'image',
                'image_preprocessing_before_ocr': preprocessing,
                'paddle_ocr_text': {
                    'available': bool(paddle_lines),
                    'confidence': paddle_confidence,
                    'raw_lines': _line_summary(paddle_lines),
                },
                'tesseract_ocr_text': {
                    'available': bool(tesseract_lines),
                    'confidence': tesseract_confidence,
                    'raw_lines': _line_summary(tesseract_lines),
                },
                'ocr_amount_line_candidates': amount_line_candidates,
                'parser_preprocessing_not_applied_here': True,
                'duration_ms': _elapsed_ms(start),
            }

        if mime_type == 'message/rfc822' or suffix == '.eml':
            plain_text, html_text = _extract_text_from_eml(file_bytes)
            return {
                **base_payload,
                'source_kind': 'email',
                'plain_text': {
                    'available': bool(plain_text.strip()),
                    'char_count': len(plain_text),
                    'excerpt': _safe_excerpt(plain_text),
                    'raw_lines': _line_summary(_normalize_text_lines(plain_text)),
                },
                'html_text': {
                    'available': bool(html_text.strip()),
                    'char_count': len(html_text),
                    'excerpt': _safe_excerpt(html_text),
                    'raw_lines': _line_summary(_normalize_text_lines(html_text)),
                },
                'duration_ms': _elapsed_ms(start),
            }

        if mime_type in {'text/html', 'text/plain'} or suffix in {'.html', '.htm', '.txt'}:
            raw_text = file_bytes.decode('utf-8', errors='ignore')
            direct_text = _html_to_text(raw_text) if (mime_type == 'text/html' or suffix in {'.html', '.htm'}) else raw_text
            return {
                **base_payload,
                'source_kind': 'text_or_html',
                'direct_text': {
                    'available': bool(direct_text.strip()),
                    'char_count': len(direct_text),
                    'excerpt': _safe_excerpt(direct_text),
                    'raw_lines': _line_summary(_normalize_text_lines(direct_text)),
                },
                'duration_ms': _elapsed_ms(start),
            }

        return {**base_payload, 'source_kind': 'unsupported', 'duration_ms': _elapsed_ms(start)}
    except Exception as exc:
        return {**base_payload, 'error': f'{exc.__class__.__name__}: {exc}', 'duration_ms': _elapsed_ms(start)}


def build_receipt_source_text_report(engine, household_id: str = '1') -> dict[str, Any]:
    start_total = _now_ms()
    with engine.begin() as conn:
        receipt_rows = _active_receipt_rows(conn, str(household_id))
    receipts = [_extract_source_text_for_receipt(row) for row in receipt_rows]
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only brontekst/OCR-tekst rapport op het vroegste tekstcreatiepunt voor alle actieve kassabonnen.',
        'scope': {
            'read_only': True,
            'active_receipts_only': True,
            'selection': 'all_active_receipts',
            'report_mode': 'source_text_created_before_parser_preprocessing',
            'parser_changed': False,
            'status_classification_changed': False,
            'database_changed': False,
            'ui_changed': False,
        },
        'summary': {
            'receipt_count': len(receipts),
            'pdf_count': sum(1 for item in receipts if item.get('source_kind') == 'pdf'),
            'image_count': sum(1 for item in receipts if item.get('source_kind') == 'image'),
            'email_count': sum(1 for item in receipts if item.get('source_kind') == 'email'),
            'unsupported_count': sum(1 for item in receipts if item.get('source_kind') == 'unsupported'),
        },
        'performance': {
            'total_duration_ms': _elapsed_ms(start_total),
            'per_receipt': [
                {
                    'filename': item.get('filename'),
                    'receipt_table_id': item.get('receipt_table_id'),
                    'source_kind': item.get('source_kind'),
                    'duration_ms': item.get('duration_ms'),
                    'error': item.get('error'),
                }
                for item in receipts
            ],
        },
        'receipts': receipts,
    }


def install_receipt_line_diagnosis_routes(app, engine) -> None:
    paths = {
        '/api/testing/receipt-line-diagnosis',
        '/api/testing/receipt-line-diagnosis/download',
        '/api/testing/receipt-source-text',
        '/api/testing/receipt-source-text/download',
    }
    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', None) not in paths]
    app.openapi_schema = None
    app.state.receipt_line_diagnosis_routes_installed = True

    @app.get('/api/testing/receipt-line-diagnosis')
    def receipt_line_diagnosis(householdId: str = '1'):
        return build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)

    @app.get('/api/testing/receipt-line-diagnosis/download')
    def receipt_line_diagnosis_download(householdId: str = '1'):
        payload = build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'rezzerv_receipt_line_diagnosis_all_active_fast_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-Rezzerv-Diagnosis-Selection': 'all_active_receipts',
                'X-Rezzerv-Diagnosis-Mode': 'stored-only-fast',
                'X-Rezzerv-Include-Live-Reparse': 'false',
                'X-Rezzerv-Include-Raw-Parser-Input': 'false',
            },
        )

    @app.get('/api/testing/receipt-source-text')
    def receipt_source_text(householdId: str = '1'):
        return build_receipt_source_text_report(engine, household_id=householdId)

    @app.get('/api/testing/receipt-source-text/download')
    def receipt_source_text_download(householdId: str = '1'):
        payload = build_receipt_source_text_report(engine, household_id=householdId)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'rezzerv_receipt_source_text_all_active_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-Rezzerv-Diagnosis-Selection': 'all_active_receipts',
                'X-Rezzerv-Diagnosis-Mode': 'source-text-before-parser',
            },
        )
