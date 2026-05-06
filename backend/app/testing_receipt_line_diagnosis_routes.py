from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Response
from sqlalchemy import text

from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline

TARGET_FILENAMES = ('Aldi foto 2.jpg', 'Lidl App 2.png')


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


def _function_trace(fn: Any) -> dict[str, Any]:
    return {
        'module': getattr(fn, '__module__', None),
        'name': getattr(fn, '__name__', None),
        'qualname': getattr(fn, '__qualname__', None),
        'id': id(fn),
        'marker_v2': bool(getattr(fn, '__rezzerv_chain_duplicate_merge_patch_v2__', False)),
        'marker_v3': bool(getattr(fn, '__rezzerv_chain_duplicate_merge_patch_v3__', False)),
    }


def _runtime_parser_trace() -> dict[str, Any]:
    from app.services import receipt_service
    main_module = sys.modules.get('app.main')
    chain_module = sys.modules.get('app.services.receipt_chain_duplicate_merge_patch')
    service_fn = getattr(receipt_service, 'parse_receipt_content', None)
    main_fn = getattr(main_module, 'parse_receipt_content', None) if main_module is not None else None
    return {
        'receipt_service_parse_receipt_content': _function_trace(service_fn),
        'app_main_parse_receipt_content': _function_trace(main_fn) if main_fn else None,
        'same_function_object': bool(service_fn is not None and main_fn is not None and service_fn is main_fn),
        'chain_patch_module_loaded': chain_module is not None,
        'chain_patch_has_apply_function': bool(chain_module is not None and hasattr(chain_module, 'apply_chain_specific_line_postprocessing')),
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


def _reparse_line_dict(line: dict[str, Any], fallback_index: int) -> dict[str, Any]:
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
    }


def _build_live_reparse(row: dict[str, Any]) -> dict[str, Any]:
    from app.services import receipt_service
    storage_path = str(row.get('storage_path') or '').strip()
    filename = str(row.get('original_filename') or 'receipt').strip() or 'receipt'
    mime_type = str(row.get('mime_type') or '').strip()
    if not storage_path:
        return {'available': False, 'error': 'storage_path_missing', 'runtime_trace': _runtime_parser_trace()}
    path = Path(storage_path)
    if not path.exists():
        return {'available': False, 'error': f'storage_file_missing:{storage_path}', 'runtime_trace': _runtime_parser_trace()}
    runtime_trace_before = _runtime_parser_trace()
    try:
        result = receipt_service.parse_receipt_content(path.read_bytes(), filename, mime_type)
        before_line_count = len(list(getattr(result, 'lines', None) or []))
        postprocess_probe = {'available': False}
        chain_module = sys.modules.get('app.services.receipt_chain_duplicate_merge_patch')
        if chain_module is not None and hasattr(chain_module, 'apply_chain_specific_line_postprocessing'):
            probe_result = chain_module.apply_chain_specific_line_postprocessing(result, filename)
            probe_lines = list(getattr(probe_result, 'lines', None) or [])
            postprocess_probe = {
                'available': True,
                'before_line_count': before_line_count,
                'after_line_count': len(probe_lines),
                'changed': len(probe_lines) != before_line_count,
                'markers': [line.get('duplicate_merge_applied') for line in probe_lines if line.get('duplicate_merge_applied')],
            }
            result = probe_result
        lines = [_reparse_line_dict(line, index) for index, line in enumerate(list(getattr(result, 'lines', None) or []))]
        return {
            'available': True,
            'runtime_trace_before_parse': runtime_trace_before,
            'runtime_trace_after_parse': _runtime_parser_trace(),
            'postprocess_probe': postprocess_probe,
            'store_name': getattr(result, 'store_name', None),
            'total_amount': _to_number(getattr(result, 'total_amount', None)),
            'discount_total': _to_number(getattr(result, 'discount_total', None)),
            'line_count': len(lines),
            'lines': lines,
        }
    except Exception as exc:  # pragma: no cover - diagnostic endpoint must be resilient
        return {'available': False, 'error': f'{exc.__class__.__name__}: {exc}', 'runtime_trace': _runtime_parser_trace()}


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


def build_receipt_line_diagnosis(engine, household_id: str = '1', filenames: list[str] | None = None) -> dict[str, Any]:
    requested = filenames or list(TARGET_FILENAMES)
    requested_keys = {_normalize_filename(name) for name in requested if _normalize_filename(name)}
    with engine.begin() as conn:
        baseline_map = _baseline_detail_map(conn, household_id=str(household_id) if household_id is not None else None)
        line_columns = {str(row.get('name')) for row in conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings().all()}
        source_index_select = ', rtl.source_index' if 'source_index' in line_columns else ''
        receipt_rows = conn.execute(
            text(
                '''
                SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rr.original_filename, rr.mime_type, rr.storage_path,
                       rt.household_id, rt.store_name, rt.store_chain, rt.total_amount, rt.discount_total, rt.line_count,
                       rt.deleted_at, rr.deleted_at AS raw_deleted_at
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
                '''
            ),
            {'household_id': str(household_id)},
        ).mappings().all()

        selected_rows = []
        for row in receipt_rows:
            row_dict = dict(row)
            if _normalize_filename(row_dict.get('original_filename')) in requested_keys:
                selected_rows.append(row_dict)

        receipts: list[dict[str, Any]] = []
        for row in selected_rows:
            receipt_id = str(row.get('receipt_table_id'))
            line_rows = conn.execute(
                text(
                    f'''
                    SELECT rtl.id, rtl.receipt_table_id, rtl.line_index, rtl.raw_label, rtl.normalized_label,
                           rtl.corrected_raw_label, rtl.quantity, rtl.corrected_quantity, rtl.unit, rtl.corrected_unit,
                           rtl.unit_price, rtl.corrected_unit_price, rtl.line_total, rtl.corrected_line_total,
                           rtl.discount_amount, rtl.barcode, rtl.confidence_score, rtl.is_deleted, rtl.is_validated
                           {source_index_select}
                    FROM receipt_table_lines rtl
                    WHERE rtl.receipt_table_id = :receipt_table_id
                    ORDER BY rtl.line_index, rtl.id
                    '''
                ),
                {'receipt_table_id': receipt_id},
            ).mappings().all()
            accepted_lines = [_receipt_line_dict(dict(line)) for line in line_rows if not line.get('is_deleted')]
            baseline = baseline_map.get(_normalize_filename(row.get('original_filename')), {})
            live_reparse = _build_live_reparse(row)
            receipts.append({
                'filename': row.get('original_filename'),
                'receipt_table_id': receipt_id,
                'store_name': row.get('store_name'),
                'store_chain': row.get('store_chain'),
                'po_norm_status_label': baseline.get('po_norm_status_label'),
                'expected_line_count': baseline.get('expected_line_count'),
                'actual_line_count': len(accepted_lines),
                'reported_line_count': _to_number(row.get('line_count')),
                'total_amount': _to_number(row.get('total_amount')),
                'discount_total': _to_number(row.get('discount_total')),
                'sum_line_total_used_for_decision': baseline.get('sum_line_total_used_for_decision'),
                'net_line_sum_used_for_decision': baseline.get('net_line_sum_used_for_decision'),
                'failed_criteria': baseline.get('failed_criteria') or [],
                'stored_accepted_lines': accepted_lines,
                'live_reparse_from_source': live_reparse,
                'diagnosis_only': True,
            })

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only line-level diagnose voor G1 met runtime parsertrace.',
        'scope': {
            'read_only': True,
            'active_receipts_only': True,
            'parser_changed': False,
            'status_classification_changed': False,
            'ui_changed': False,
            'target_filenames': requested,
            'status_source': 'receipt_status_baseline_service_v4.py via po_norm_status_label',
        },
        'runtime_parser_trace': _runtime_parser_trace(),
        'summary': {
            'requested': len(requested),
            'returned': len(receipts),
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
    def receipt_line_diagnosis(householdId: str = '1', filenames: str | None = None):
        return build_receipt_line_diagnosis(engine, household_id=householdId, filenames=_parse_filename_query(filenames))

    @app.get('/api/testing/receipt-line-diagnosis/download')
    def receipt_line_diagnosis_download(householdId: str = '1', filenames: str | None = None):
        payload = build_receipt_line_diagnosis(engine, household_id=householdId, filenames=_parse_filename_query(filenames))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'rezzerv_receipt_line_diagnosis_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
