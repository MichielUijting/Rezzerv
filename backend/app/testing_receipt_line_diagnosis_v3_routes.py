from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import Response

from app.testing_receipt_line_diagnosis_routes import build_receipt_line_diagnosis

ROUTE_VERSION = 'receipt-line-diagnosis-v3-runtime-trace'


def _parse_filename_query(filenames: str | None) -> list[str] | None:
    if not filenames:
        return None
    values = [item.strip() for item in str(filenames).split(',') if item.strip()]
    return values or None


def _build_payload(engine, household_id: str = '1', filenames: str | None = None):
    payload = build_receipt_line_diagnosis(
        engine,
        household_id=household_id,
        filenames=_parse_filename_query(filenames),
    )
    payload['route_version'] = ROUTE_VERSION
    payload['route_generated_at'] = datetime.now(timezone.utc).isoformat()
    return payload


def install_receipt_line_diagnosis_v3_routes(app, engine) -> None:
    paths = {
        '/api/testing/receipt-line-diagnosis-v3',
        '/api/testing/receipt-line-diagnosis-v3/download',
    }
    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', None) not in paths]
    app.state.receipt_line_diagnosis_v3_routes_installed = True

    @app.get('/api/testing/receipt-line-diagnosis-v3')
    def receipt_line_diagnosis_v3(householdId: str = '1', filenames: str | None = None):
        payload = _build_payload(engine, household_id=householdId, filenames=filenames)
        return Response(
            content=json.dumps(payload, ensure_ascii=False),
            media_type='application/json',
            headers={'Cache-Control': 'no-store'},
        )

    @app.get('/api/testing/receipt-line-diagnosis-v3/download')
    def receipt_line_diagnosis_v3_download(householdId: str = '1', filenames: str | None = None):
        payload = _build_payload(engine, household_id=householdId, filenames=filenames)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="rezzerv_receipt_line_diagnosis_v3_{timestamp}.json"',
                'Cache-Control': 'no-store',
            },
        )
