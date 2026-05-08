from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from app.db import engine
from app.testing_receipt_line_diagnosis_routes import build_receipt_line_diagnosis
from app.testing_receipt_parser_diagnosis_routes import build_receipt_parser_diagnosis

router = APIRouter(
    prefix="/api/testing",
    tags=["receipt-diagnosis"],
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
