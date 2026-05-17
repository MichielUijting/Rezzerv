from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Response, UploadFile

from app.db import engine
from app.testing_receipt_line_diagnosis_routes import build_receipt_line_diagnosis
from app.testing_receipt_parser_diagnosis_routes import build_receipt_parser_diagnosis
from receipt_ingestion.kassa_kpi_baseline import build_kassa_kpi_baseline
from receipt_ingestion.kassa_kpi_scope_diagnosis import build_kassa_kpi_scope_diagnosis
from app.api.receipt_import_diagnosis_routes import (
    diagnose_receipt_zip_import,
    get_receipt_import_diagnosis_health,
)

router = APIRouter(
    prefix='/api/receipt-diagnostics',
    tags=['receipt-diagnostics'],
)


@router.get('/route-inventory')
def get_receipt_diagnostics_route_inventory() -> dict[str, Any]:
    """Read-only inventory of receipt-related diagnostic APIs.

    This endpoint is intentionally static: it documents the consolidation plan
    and prevents new ad-hoc diagnostic endpoints from becoming the source of truth.
    """
    return {
        'success': True,
        'diagnostic_only': True,
        'parser_changed': False,
        'status_classification_changed': False,
        'database_changed': False,
        'canonical_routes': [
            {
                'path': '/api/receipt-diagnostics/line-quality',
                'method': 'GET',
                'purpose': 'Canonical line-level quality report for active receipts.',
                'source': 'build_receipt_line_diagnosis',
            },
            {
                'path': '/api/receipt-diagnostics/line-quality/download',
                'method': 'GET',
                'purpose': 'Downloadable line-level quality report.',
                'source': 'build_receipt_line_diagnosis',
            },
            {
                'path': '/api/receipt-diagnostics/parser-quality',
                'method': 'GET',
                'purpose': 'Parser-oriented diagnosis for active receipts.',
                'source': 'build_receipt_parser_diagnosis',
            },
            {
                'path': '/api/receipt-diagnostics/kpi',
                'method': 'GET',
                'purpose': 'Current Gecontroleerd/Controle nodig KPI baseline.',
                'source': 'build_kassa_kpi_baseline',
            },
            {
                'path': '/api/receipt-diagnostics/import-dry-run',
                'method': 'POST',
                'purpose': 'ZIP import preflight without database writes.',
                'source': 'diagnose_receipt_zip_import',
            },
        ],
        'legacy_routes_to_deprecate_after_validation': [
            '/api/testing/receipt-line-diagnosis',
            '/api/testing/receipt-line-diagnosis/download',
            '/api/testing/receipt-parser-diagnosis',
            '/api/testing/receipt-parser-diagnosis/download',
            '/api/receipt-import-diagnosis/health',
            '/api/receipt-import-diagnosis/zip-dry-run',
            '/api/receipt-kpi/baseline',
            '/api/receipt-kpi/scope-diagnosis',
        ],
        'temporary_routes_that_must_not_return': [
            '/api/testing/receipt-filter-selftest',
            '/api/testing/receipt-line-flow-trace',
            '/api/testing/receipt-table-schema',
            '/api/testing/reset-active-receipt-testset',
        ],
    }


@router.get('/line-quality')
def get_receipt_line_quality(householdId: str = '1', filenames: str | None = None):
    return build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)


@router.get('/line-quality/download')
def download_receipt_line_quality(householdId: str = '1', filenames: str | None = None):
    payload = build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'rezzerv_receipt_line_quality_{timestamp}.json'
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Rezzerv-Diagnosis-Selection': 'all_active_receipts',
        },
    )


@router.get('/parser-quality')
def get_receipt_parser_quality(householdId: str = '1'):
    return build_receipt_parser_diagnosis(engine, householdId)


@router.get('/parser-quality/download')
def download_receipt_parser_quality(householdId: str = '1'):
    payload = build_receipt_parser_diagnosis(engine, householdId)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'rezzerv_receipt_parser_quality_{timestamp}.json'
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.get('/kpi')
def get_receipt_diagnostics_kpi():
    with engine.begin() as conn:
        return build_kassa_kpi_baseline(conn)


@router.get('/kpi/scope')
def get_receipt_diagnostics_kpi_scope():
    with engine.begin() as conn:
        return build_kassa_kpi_scope_diagnosis(conn)


@router.get('/import-dry-run/health')
def get_import_dry_run_health():
    return get_receipt_import_diagnosis_health()


@router.post('/import-dry-run')
async def post_import_dry_run(file: UploadFile = File(...)):
    return await diagnose_receipt_zip_import(file)
