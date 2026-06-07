"""
Technical Design Reference:
- TD Section: TD-07 Diagnose en explainability
- Module Role: Diagnostic or test API route
- Runtime Type: diagnostic
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: keep_diagnostic
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

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

ROUTE_INVENTORY_PATH = Path(
    os.getenv(
        'REZZERV_RECEIPT_DIAGNOSTICS_ROUTE_INVENTORY',
        '/app/tools/receipt_csv_poc/reports/receipt_diagnostics_route_inventory.json',
    )
)


@router.get('/route-inventory')
def get_receipt_diagnostics_route_inventory():
    with ROUTE_INVENTORY_PATH.open('r', encoding='utf-8') as handle:
        return json.load(handle)


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
