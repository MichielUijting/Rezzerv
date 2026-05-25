from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Response
from sqlalchemy import text

from app.services.receipt_service import parse_receipt_content
from app.receipt_ingestion.line_classifier import diagnose_article_line_classification
from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload
from app.receipt_ingestion.profiles.ah_runtime import AH_SAVINGS_STAMPS_RE
from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline


def _bool_query(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'ja', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'nee', 'off'}:
        return False
    return default


def _parse_limit(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


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


def _diagnostic_line_diagnosis(value: Any, *, store_name: str | None, filename: str | None) -> dict[str, Any]:
    try:
        return diagnose_article_line_classification(
            str(value or ''),
            store_name=store_name,
            filename=filename,
        )
    except Exception as exc:
        fallback = f'classification_error:{exc.__class__.__name__}'
        return {
            'raw_line': value,
            'normalized_line': str(value or '').strip(),
            'store_name': store_name,
            'filename': filename,
            'classification': fallback,
            'article_decision': 'GEEN_ARTIKEL',
            'include_in_article_sum': False,
            'reason': fallback,
            'rule': 'DIAGNOSIS_EXCEPTION',
            'stage': 'diagnosis_error',
            'matched': None,
            'trace': {'classification': fallback},
            'extra_context': {},
        }


def _build_raw_line_diagnostics(raw_lines: list[str], *, filename: str, store_name: str | None) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines or [], start=1):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        diagnosis = _diagnostic_line_diagnosis(normalized, store_name=store_name, filename=filename)
        diagnostics.append({
            'line_number': index,
            'raw_line': raw_line,
            'normalized_line': normalized,
            'classification': diagnosis.get('classification'),
            'article_decision': diagnosis.get('article_decision'),
            'include_in_article_sum': diagnosis.get('include_in_article_sum'),
            'reason': diagnosis.get('reason'),
            'rule': diagnosis.get('rule'),
            'stage': diagnosis.get('stage'),
            'matched': diagnosis.get('matched'),
            'ah_savings_stamps_match': bool(AH_SAVINGS_STAMPS_RE.match(normalized.lower())),
            'contains_diagnostic_terms': [
                term for term in ('koopzegels', 'bonus', 'bbox', 'uw voordeel', 'subtotaal', 'totaal')
                if term in normalized.lower()
            ],
        })
    return diagnostics


def _build_producer_trace(line: dict[str, Any], *, filename: str, store_name: str | None) -> dict[str, Any]:
    existing_trace = line.get('producer_trace') if isinstance(line.get('producer_trace'), dict) else {}
    label = line.get('normalized_label') or line.get('raw_label')
    diagnosis = _diagnostic_line_diagnosis(label, store_name=store_name, filename=filename)

    classification = existing_trace.get('classification') or diagnosis.get('classification')
    rule = existing_trace.get('classification_rule') or diagnosis.get('rule')
    stage = existing_trace.get('classification_stage') or diagnosis.get('stage')
    matched = existing_trace.get('classification_matched') or diagnosis.get('matched')
    trace = existing_trace.get('classification_trace') or diagnosis.get('trace')

    return {
        'filename': existing_trace.get('filename') or filename,
        'store_name': existing_trace.get('store_name') or store_name,
        'parser_path': existing_trace.get('parser_path') or 'parse_receipt_content.result_line',
        'source_index': existing_trace.get('source_index') if 'source_index' in existing_trace else line.get('source_index'),
        'normalized_line': existing_trace.get('normalized_line') or line.get('normalized_label') or line.get('raw_label'),
        'label': existing_trace.get('label') or label,
        'amount': _to_number(existing_trace.get('amount') if 'amount' in existing_trace else line.get('line_total')),
        'classification': classification,
        'classification_rule': rule,
        'classification_stage': stage,
        'classification_matched': matched,
        'classification_trace': trace,
        'article_decision': diagnosis.get('article_decision'),
        'include_in_article_sum': diagnosis.get('include_in_article_sum'),
        'reason': diagnosis.get('reason'),
        'append_allowed': existing_trace.get('append_allowed') if 'append_allowed' in existing_trace else True,
        'classification_allows_append': classification not in {'ignore', 'metadata', 'footer_payment_tax'},
        'trace_source': 'parser_trace_plus_existing_line_diagnosis' if existing_trace else 'existing_line_diagnosis',
    }


def _reparse_line_dict(line: dict[str, Any], fallback_index: int, *, filename: str, store_name: str | None) -> dict[str, Any]:
    return {
        'line_number': fallback_index + 1,
        'raw_label': line.get('raw_label'),
        'normalized_label': line.get('normalized_label'),
        'quantity': _to_number(line.get('quantity')),
        'unit': line.get('unit'),
        'unit_price': _to_number(line.get('unit_price')),
        'line_total': _to_number(line.get('line_total')),
        'discount_amount': _to_number(line.get('discount_amount')),
        'barcode': line.get('barcode'),
        'confidence_score': _to_number(line.get('confidence_score')),
        'source_index': line.get('source_index'),
        'duplicate_merge_applied': line.get('duplicate_merge_applied'),
        'merged_companion_label': line.get('merged_companion_label'),
        'producer_trace': _build_producer_trace(line, filename=filename, store_name=store_name),
    }


def _extract_raw_text_lines_from_result(result: Any) -> list[str]:
    diagnostics = getattr(result, 'parser_diagnostics', None)
    if not isinstance(diagnostics, dict):
        return []
    for key in (
        'raw_text_lines_before_extract_receipt_lines',
        'raw_text_lines',
        'text_lines',
        'source_text_lines',
    ):
        value = diagnostics.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _build_live_reparse(
    row: dict[str, Any],
    *,
    include_raw_parser_input: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    timing: dict[str, Any] = {'storage_read_duration_ms': 0, 'parse_duration_ms': 0, 'total_duration_ms': 0}
    start_total = _now_ms()
    storage_path = str(row.get('storage_path') or '').strip()
    filename = str(row.get('original_filename') or 'receipt').strip() or 'receipt'
    mime_type = str(row.get('mime_type') or '').strip()
    if not storage_path:
        timing['total_duration_ms'] = _elapsed_ms(start_total)
        return {'available': False, 'error': 'storage_path_missing'}, timing
    path = Path(storage_path)
    if not path.exists():
        timing['total_duration_ms'] = _elapsed_ms(start_total)
        return {'available': False, 'error': f'storage_file_missing:{storage_path}'}, timing
    try:
        read_start = _now_ms()
        source_bytes = path.read_bytes()
        timing['storage_read_duration_ms'] = _elapsed_ms(read_start)
        parse_start = _now_ms()
        result = parse_receipt_content(source_bytes, filename, mime_type)
        timing['parse_duration_ms'] = _elapsed_ms(parse_start)
        store_name = getattr(result, 'store_name', None)
        lines = [
            _reparse_line_dict(line, index, filename=filename, store_name=store_name)
            for index, line in enumerate(list(getattr(result, 'lines', None) or []))
        ]
        payload = {
            'available': True,
            'store_name': store_name,
            'total_amount': _to_number(getattr(result, 'total_amount', None)),
            'discount_total': _to_number(getattr(result, 'discount_total', None)),
            'line_count': len(lines),
            'lines': lines,
        }
        if include_raw_parser_input:
            raw_lines = _extract_raw_text_lines_from_result(result)
            payload['raw_parser_input'] = {
                'available': bool(raw_lines),
                'reason': None if raw_lines else 'raw_text_lines_not_exposed_by_parse_receipt_content',
                'raw_text_lines_before_extract_receipt_lines': raw_lines,
                'line_classification_per_raw_text_line': _build_raw_line_diagnostics(raw_lines, filename=filename, store_name=store_name),
                'extracted_lines_after_parser': lines,
                'parser_debug_payload': build_parser_debug_payload(result),
            }
        timing['total_duration_ms'] = _elapsed_ms(start_total)
        return payload, timing
    except Exception as exc:
        timing['total_duration_ms'] = _elapsed_ms(start_total)
        return {'available': False, 'error': f'{exc.__class__.__name__}: {exc}'}, timing


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


def build_receipt_line_diagnosis(
    engine,
    household_id: str = '1',
    filenames: list[str] | None = None,
    *,
    include_live_reparse: bool = False,
    include_raw_parser_input: bool = False,
    only_failed: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    # SSOT: line-level diagnosis analyses all active receipts by default.
    # The filenames argument is kept for backward-compatible callers but is deliberately ignored.
    requested: list[str] = []
    start_total = _now_ms()
    per_receipt_perf: list[dict[str, Any]] = []
    live_reparse_count = 0
    raw_parser_input_count = 0
    with engine.begin() as conn:
        baseline_map = _baseline_detail_map(conn, household_id=str(household_id) if household_id is not None else None)
        line_columns = {str(row.get('name')) for row in conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings().all()}
        source_index_select = ', rtl.source_index' if 'source_index' in line_columns else ''
        receipt_rows = conn.execute(
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

        receipts: list[dict[str, Any]] = []
        for row in receipt_rows:
            receipt_start = _now_ms()
            row_dict = dict(row)
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
            receipt_payload: dict[str, Any] = {
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
            }
            should_live_reparse = include_live_reparse
            if should_live_reparse and only_failed and not failed_criteria:
                should_live_reparse = False
            if should_live_reparse and limit is not None and live_reparse_count >= limit:
                should_live_reparse = False
                receipt_payload['live_reparse_from_source'] = {'available': False, 'skipped': True, 'reason': 'live_reparse_limit_reached'}

            reparse_timing: dict[str, Any] | None = None
            if should_live_reparse:
                live_payload, reparse_timing = _build_live_reparse(
                    row_dict,
                    include_raw_parser_input=include_raw_parser_input,
                )
                receipt_payload['live_reparse_from_source'] = live_payload
                live_reparse_count += 1
                if include_raw_parser_input:
                    raw_parser_input_count += 1
            elif 'live_reparse_from_source' not in receipt_payload:
                receipt_payload['live_reparse_from_source'] = {
                    'available': False,
                    'skipped': True,
                    'reason': 'includeLiveReparse=false' if not include_live_reparse else 'onlyFailed=true_and_receipt_has_no_failed_criteria',
                }

            receipts.append(receipt_payload)
            perf_item = {
                'filename': row_dict.get('original_filename'),
                'receipt_table_id': receipt_id,
                'duration_ms': _elapsed_ms(receipt_start),
                'live_reparse_executed': bool(reparse_timing),
                'live_reparse_duration_ms': (reparse_timing or {}).get('total_duration_ms', 0),
                'storage_read_duration_ms': (reparse_timing or {}).get('storage_read_duration_ms', 0),
                'parse_duration_ms': (reparse_timing or {}).get('parse_duration_ms', 0),
            }
            per_receipt_perf.append(perf_item)

    total_duration = _elapsed_ms(start_total)
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only line-level diagnose; gebruikt alle actieve kassabonnen.',
        'scope': {
            'read_only': True,
            'active_receipts_only': True,
            'parser_changed': False,
            'status_classification_changed': False,
            'ui_changed': False,
            'target_filenames': requested,
            'selection': 'all_active_receipts',
            'status_source': 'receipt_status_baseline_service_v4.py via po_norm_status_label',
            'producer_trace_added': True,
            'includeLiveReparse': bool(include_live_reparse),
            'includeRawParserInput': bool(include_raw_parser_input),
            'onlyFailed': bool(only_failed),
            'limit': limit,
        },
        'summary': {'requested': 'all_active_receipts', 'returned': len(receipts)},
        'performance': {
            'total_duration_ms': total_duration,
            'receipt_count': len(receipts),
            'live_reparse_count': live_reparse_count,
            'raw_parser_input_count': raw_parser_input_count,
            'per_receipt': per_receipt_perf,
        },
        'receipts': receipts,
    }


def _parse_filename_query(filenames: str | None) -> list[str] | None:
    if not filenames:
        return None
    values = [item.strip() for item in str(filenames).split(',') if item.strip()]
    return values or None


def install_receipt_line_diagnosis_routes(app, engine) -> None:
    paths = {'/api/testing/receipt-line-diagnosis', '/api/testing/receipt-line-diagnosis/download'}
    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', None) not in paths]
    app.state.receipt_line_diagnosis_routes_installed = True

    @app.get('/api/testing/receipt-line-diagnosis')
    def receipt_line_diagnosis(
        householdId: str = '1',
        filenames: str | None = None,
        includeLiveReparse: bool = False,
        includeRawParserInput: bool = False,
        onlyFailed: bool = False,
        limit: int | None = None,
    ):
        return build_receipt_line_diagnosis(
            engine,
            household_id=householdId,
            filenames=None,
            include_live_reparse=_bool_query(includeLiveReparse),
            include_raw_parser_input=_bool_query(includeRawParserInput),
            only_failed=_bool_query(onlyFailed),
            limit=_parse_limit(limit),
        )

    @app.get('/api/testing/receipt-line-diagnosis/download')
    def receipt_line_diagnosis_download(
        householdId: str = '1',
        filenames: str | None = None,
        includeLiveReparse: bool = False,
        includeRawParserInput: bool = False,
        onlyFailed: bool = False,
        limit: int | None = None,
    ):
        include_live_reparse = _bool_query(includeLiveReparse)
        include_raw_parser_input = _bool_query(includeRawParserInput)
        only_failed = _bool_query(onlyFailed)
        parsed_limit = _parse_limit(limit)
        payload = build_receipt_line_diagnosis(
            engine,
            household_id=householdId,
            filenames=None,
            include_live_reparse=include_live_reparse,
            include_raw_parser_input=include_raw_parser_input,
            only_failed=only_failed,
            limit=parsed_limit,
        )
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        mode = 'deep' if include_live_reparse else 'fast'
        filename = f'rezzerv_receipt_line_diagnosis_all_active_{mode}_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-Rezzerv-Diagnosis-Selection': 'all_active_receipts',
                'X-Rezzerv-Diagnosis-Mode': mode,
                'X-Rezzerv-Include-Live-Reparse': str(include_live_reparse).lower(),
                'X-Rezzerv-Include-Raw-Parser-Input': str(include_raw_parser_input).lower(),
            },
        )