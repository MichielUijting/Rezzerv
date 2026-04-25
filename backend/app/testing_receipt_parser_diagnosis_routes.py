from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Response
from sqlalchemy import text


def _status_label(parse_status: Any) -> str:
    status = str(parse_status or '').strip().lower()
    if status in {'approved', 'parsed', 'approved_override'}:
        return 'Gecontroleerd'
    if status in {'review_needed', 'partial'}:
        return 'Controle nodig'
    return 'Handmatig'


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


def _receipt_line_dict(row: dict[str, Any]) -> dict[str, Any]:
    label = row.get('corrected_raw_label') or row.get('raw_label') or row.get('normalized_label')
    return {
        'id': row.get('id'),
        'line_number': int(row.get('line_index') or 0) + 1,
        'text': label,
        'article_name': label,
        'raw_label': row.get('raw_label'),
        'normalized_label': row.get('normalized_label'),
        'corrected_raw_label': row.get('corrected_raw_label'),
        'quantity': _to_number(row.get('corrected_quantity') if row.get('corrected_quantity') is not None else row.get('quantity')),
        'unit': row.get('corrected_unit') or row.get('unit'),
        'unit_price': _to_number(row.get('corrected_unit_price') if row.get('corrected_unit_price') is not None else row.get('unit_price')),
        'line_total': _to_number(row.get('corrected_line_total') if row.get('corrected_line_total') is not None else row.get('line_total')),
        'discount_amount': _to_number(row.get('discount_amount')),
        'barcode': row.get('barcode'),
        'matched_article_id': row.get('matched_article_id'),
        'matched_global_product_id': row.get('matched_global_product_id'),
        'article_match_status': row.get('article_match_status'),
        'confidence_score': _to_number(row.get('confidence_score')),
        'is_deleted': bool(row.get('is_deleted') or 0),
        'is_validated': bool(row.get('is_validated') or 0),
    }


def build_receipt_parser_diagnosis(engine, household_id: str = '1') -> dict[str, Any]:
    with engine.begin() as conn:
        datastore = conn.execute(text('PRAGMA database_list')).mappings().all()
        database_path = ''
        for row in datastore:
            if row.get('name') == 'main':
                database_path = str(row.get('file') or '')
                break

        receipt_rows = conn.execute(
            text(
                '''
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rr.original_filename AS filename,
                    rt.household_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.line_count,
                    rt.created_at,
                    rt.updated_at,
                    rr.raw_status
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

        receipt_ids = [str(row['receipt_table_id']) for row in receipt_rows]
        line_map: dict[str, list[dict[str, Any]]] = {receipt_id: [] for receipt_id in receipt_ids}
        if receipt_ids:
            placeholders = ','.join(f':id_{index}' for index, _ in enumerate(receipt_ids))
            params = {f'id_{index}': receipt_id for index, receipt_id in enumerate(receipt_ids)}
            line_rows = conn.execute(
                text(
                    f'''
                    SELECT
                        id, receipt_table_id, line_index,
                        raw_label, normalized_label, corrected_raw_label,
                        quantity, corrected_quantity, unit, corrected_unit,
                        unit_price, corrected_unit_price, line_total, corrected_line_total,
                        discount_amount, barcode, matched_article_id, matched_global_product_id,
                        article_match_status, confidence_score, is_deleted, is_validated
                    FROM receipt_table_lines
                    WHERE receipt_table_id IN ({placeholders})
                    ORDER BY receipt_table_id, line_index, id
                    '''
                ),
                params,
            ).mappings().all()
            for row in line_rows:
                line_map.setdefault(str(row['receipt_table_id']), []).append(dict(row))

        column_rows = conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings().all()
        line_columns = [str(row.get('name')) for row in column_rows]

    receipts: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    total_lines = 0
    lines_with_label = 0

    for row in receipt_rows:
        row_dict = dict(row)
        receipt_id = str(row_dict['receipt_table_id'])
        accepted_lines = []
        for line in line_map.get(receipt_id, []):
            if line.get('is_deleted'):
                continue
            parsed_line = _receipt_line_dict(line)
            accepted_lines.append(parsed_line)
            total_lines += 1
            if parsed_line.get('raw_label') or parsed_line.get('normalized_label') or parsed_line.get('corrected_raw_label') or parsed_line.get('article_name'):
                lines_with_label += 1

        line_sum = round(sum(float(line.get('line_total') or 0) for line in accepted_lines), 2)
        discount_sum = round(sum(float(line.get('discount_amount') or 0) for line in accepted_lines), 2)
        total_amount = _to_number(row_dict.get('total_amount'))
        difference = None
        if total_amount is not None:
            difference = round(float(total_amount) - line_sum, 2)

        label = _status_label(row_dict.get('parse_status'))
        status_counts[label] = status_counts.get(label, 0) + 1
        receipts.append({
            'filename': row_dict.get('filename'),
            'receipt_table_id': receipt_id,
            'raw_receipt_id': row_dict.get('raw_receipt_id'),
            'household_id': row_dict.get('household_id'),
            'store_name': row_dict.get('store_name'),
            'store_branch': row_dict.get('store_branch'),
            'purchase_at': row_dict.get('purchase_at'),
            'parse_status': row_dict.get('parse_status'),
            'status_label_nl': label,
            'confidence_score': _to_number(row_dict.get('confidence_score')),
            'ocr_lines': [],
            'normalized_lines': [],
            'accepted_lines': accepted_lines,
            'rejected_lines': [],
            'financials': {
                'total_amount': total_amount,
                'line_sum': line_sum,
                'discount_sum': discount_sum,
                'difference': difference,
                'line_count_reported': _to_number(row_dict.get('line_count')),
                'line_count_actual': len(accepted_lines),
            },
            'status_decision': {
                'parse_status': row_dict.get('parse_status'),
                'status_label_nl': label,
                'raw_status': row_dict.get('raw_status'),
                'source': 'receipt_tables.parse_status',
            },
            'diagnosis_notes': [
                'Read-only diagnose: parser, OCR, statusclassificatie en UI worden niet gewijzigd.',
                'Ruwe OCR-regels en parser-afwijzingsredenen zijn alleen beschikbaar als ze al in de database worden opgeslagen.',
                'Gevonden receipt_table_lines-kolommen: ' + ', '.join(line_columns),
            ],
        })

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Rezzerv receipt parser diagnose voor generieke parserverbetering zonder bonspecifieke fixes.',
        'runtime_datastore': {
            'datastore': 'sqlite',
            'database_url': 'sqlite:////app/data/rezzerv.db',
            'database': database_path or '/app/data/rezzerv.db',
            'storage': 'sqlite_data',
        },
        'summary': {
            'returned_receipts': len(receipts),
            'status_counts_nl': status_counts,
            'accepted_lines_total': total_lines,
            'accepted_lines_with_label': lines_with_label,
        },
        'diagnosis_scope': {
            'read_only': True,
            'parser_changed': False,
            'ocr_changed': False,
            'status_classification_changed': False,
            'ui_changed': False,
            'bonspecific_fixes': False,
        },
        'receipts': receipts,
    }


def install_receipt_parser_diagnosis_routes(app, engine) -> None:
    if getattr(app.state, 'receipt_parser_diagnosis_routes_installed', False):
        return
    app.state.receipt_parser_diagnosis_routes_installed = True

    @app.get('/api/testing/receipt-parser-diagnosis')
    def receipt_parser_diagnosis(householdId: str = '1'):
        return build_receipt_parser_diagnosis(engine, householdId)

    @app.get('/api/testing/receipt-parser-diagnosis/download')
    def receipt_parser_diagnosis_download(householdId: str = '1'):
        payload = build_receipt_parser_diagnosis(engine, householdId)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'rezzerv_receipt_parser_diagnosis_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
