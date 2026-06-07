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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.debug_artifact_store import read_ingest_debug_artifact_for_receipt
from app.testing_receipt_line_diagnosis_routes import build_receipt_line_diagnosis
from app.testing_receipt_parser_diagnosis_routes import build_receipt_parser_diagnosis

router = APIRouter(
    prefix="/api/testing",
    tags=["receipt-diagnosis"],
)

RECEIPT_STORAGE_ROOT = Path('/app/data/receipts/raw')


def _debug_download_response(payload: dict, filename_hint: str) -> Response:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    safe_hint = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '-' for ch in filename_hint).strip('-') or 'receipt'
    filename = f'rezzerv-kassa-ingest-debug-{safe_hint}-{timestamp}.json'
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Rezzerv-Debug-Artifact': 'persisted-ingest-json',
            'X-Rezzerv-Debug-Reparse': 'disabled',
        },
    )


@router.get('/receipt-line-diagnosis')
def receipt_line_diagnosis(householdId: str = '1', filenames: str | None = None):
    """Read-only line-level diagnosis for all active receipts.

    SSOT guardrail: this endpoint only reports diagnostics. It does not change
    parser output, OCR output, receipt status classification, UI state or data.
    """
    return build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)


@router.get('/receipt-line-diagnosis/download')
def receipt_line_diagnosis_download(householdId: str = '1', filenames: str | None = None):
    payload = build_receipt_line_diagnosis(engine, household_id=householdId, filenames=None)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'rezzerv_receipt_line_diagnosis_all_active_{timestamp}.json'
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


@router.get('/receipt-parser-diagnosis')
def receipt_parser_diagnosis(householdId: str = '1'):
    """Read-only parser diagnosis for active receipts."""
    return build_receipt_parser_diagnosis(engine, householdId)


@router.get('/receipt-parser-diagnosis/download')
def receipt_parser_diagnosis_download(householdId: str = '1'):
    payload = build_receipt_parser_diagnosis(engine, householdId)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'rezzerv_receipt_parser_diagnosis_{timestamp}.json'
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.get('/receipts/latest/ingest-debug/download')
def latest_receipt_ingest_debug_download(householdId: str = '1'):
    """Find the latest active receipt and download its ingest-debug JSON."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT rt.id AS receipt_table_id, rt.raw_receipt_id
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                ORDER BY rt.created_at DESC, rt.id DESC
                LIMIT 1
                """
            ),
            {'household_id': str(householdId or '1')},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Geen kassabon gevonden voor dit huishouden')
    payload = read_ingest_debug_artifact_for_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        receipt_table_id=str(row['receipt_table_id']),
    )
    payload['selection'] = {
        'mode': 'latest_active_receipt',
        'household_id': str(householdId or '1'),
        'receipt_table_id': str(row['receipt_table_id']),
        'raw_receipt_id': str(row['raw_receipt_id']),
    }
    return _debug_download_response(payload, f"latest-{row['raw_receipt_id']}")


@router.get('/receipts/{receipt_table_id}/ingest-debug/download')
def receipt_ingest_debug_download(receipt_table_id: str):
    """Download the persisted ingest-debug JSON without OCR or reparse."""
    payload = read_ingest_debug_artifact_for_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        receipt_table_id=receipt_table_id,
    )
    raw_id = str(payload.get('raw_receipt_id') or receipt_table_id)
    return _debug_download_response(payload, raw_id)
