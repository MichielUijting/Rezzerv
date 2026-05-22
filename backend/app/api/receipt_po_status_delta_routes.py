from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from app.db import engine
from app.services.receipt_status_baseline_service_v4 import (
    diagnose_receipt_status_baseline,
    validate_receipt_status_baseline,
)

router = APIRouter(
    prefix='/api/testing',
    tags=['receipt-po-status-delta'],
)


def build_po_status_delta_report(household_id: str = '1') -> dict:
    """Read-only SSOT PO delta analysis.

    Guardrails:
    - no parser changes
    - no OCR changes
    - no UI changes
    - no status override
    - po_norm_status_label remains source of truth
    """
    with engine.begin() as conn:
        validation = validate_receipt_status_baseline(conn, household_id=household_id)
        diagnosis = diagnose_receipt_status_baseline(conn, household_id=household_id)

    rows = []
    for item in validation.get('details', []):
        criteria = item.get('criteria') or {}
        rows.append({
            'source_file': item.get('source_file'),
            'receipt_table_id': item.get('receipt_table_id'),
            'matched_original_filename': item.get('matched_original_filename'),
            'store_expected': item.get('expected_store_chain') or criteria.get('expected_store_chain') or item.get('expected_store_name'),
            'store_actual': item.get('store_chain') or criteria.get('actual_store_chain') or item.get('store_name'),
            'baseline_total': item.get('expected_total_amount'),
            'actual_total': item.get('total_amount'),
            'baseline_article_count': item.get('expected_line_count'),
            'actual_article_count': item.get('line_count'),
            'sum_articles': item.get('net_line_sum_used_for_decision'),
            'discount_total_used_for_decision': item.get('discount_total_used_for_decision'),
            'po_norm_status': item.get('po_norm_status'),
            'po_norm_status_label': item.get('po_norm_status_label'),
            'technical_parse_status': item.get('technical_parse_status'),
            'technical_parse_status_label': item.get('technical_parse_status_label'),
            'failed_criteria': item.get('failed_criteria') or [],
            'delta_reason': item.get('difference_reason') or item.get('reason'),
            'store_matches_baseline': criteria.get('store_chain_matches_baseline'),
            'total_matches_baseline': criteria.get('total_amount_matches_baseline'),
            'article_count_matches_baseline': criteria.get('article_count_matches_baseline'),
            'line_sum_matches_total': criteria.get('line_sum_matches_total'),
            'status_source': 'receipt_status_baseline_service_v4.py',
        })

    return {
        'report_name': 'R7c-20B PO-statusdelta-analyse',
        'report_mode': 'read_only_diagnosis',
        'status_source': 'receipt_status_baseline_service_v4.py',
        'status_field': 'po_norm_status_label',
        'summary': validation.get('summary', {}),
        'delta_rows': rows,
        'diagnosis': diagnosis,
        'excluded_archived_receipts': validation.get('excluded_archived_receipts', []),
        'runtime_datastore': validation.get('runtime_datastore'),
    }


@router.get('/receipt-po-status-delta')
def receipt_po_status_delta(householdId: str = '1'):
    return build_po_status_delta_report(household_id=householdId)


@router.get('/receipt-po-status-delta/download')
def receipt_po_status_delta_download(householdId: str = '1'):
    payload = build_po_status_delta_report(household_id=householdId)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'rezzerv_po_status_delta_r7c20b_{timestamp}.json'
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Rezzerv-Status-Source': 'receipt_status_baseline_service_v4.py',
        },
    )
