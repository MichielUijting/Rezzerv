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
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

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
PACKAGE_UNITS = {'g', 'gr', 'gram', 'kg', 'ml', 'cl', 'l', 'liter'}


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


def _normalize_spaces(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _json_number(value: Any) -> Any:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _line_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        normalized = _normalize_spaces(row.get(key))
        if normalized:
            return normalized
    return ''


def _article_name(row: dict[str, Any]) -> str:
    return _line_text(row, 'display_label', 'corrected_raw_label', 'normalized_label', 'raw_label')


def _raw_line(row: dict[str, Any]) -> str:
    return _line_text(row, 'raw_label', 'corrected_raw_label', 'display_label', 'normalized_label')


def _clean_line(row: dict[str, Any]) -> str:
    return _line_text(row, 'normalized_label', 'display_label', 'corrected_raw_label', 'raw_label')


def _quantity_value(row: dict[str, Any]) -> Any:
    return row.get('display_quantity') if row.get('display_quantity') is not None else row.get('corrected_quantity') if row.get('corrected_quantity') is not None else row.get('quantity')


def _unit_value(row: dict[str, Any]) -> str:
    return _line_text(row, 'display_unit', 'corrected_unit', 'unit')


def _line_price(row: dict[str, Any]) -> Any:
    return row.get('display_line_total') if row.get('display_line_total') is not None else row.get('corrected_line_total') if row.get('corrected_line_total') is not None else row.get('line_total')


def _package_size_label(row: dict[str, Any]) -> str | None:
    quantity = _quantity_value(row)
    unit = _unit_value(row)
    if quantity is None or quantity == '':
        return None
    quantity_text = str(_json_number(quantity)).replace('.', ',')
    return f"{quantity_text} {unit}".strip() if unit else quantity_text


def _off_query(row: dict[str, Any]) -> str:
    article = _article_name(row).lower()
    quantity = _quantity_value(row)
    unit = _unit_value(row).lower()
    if article and quantity not in {None, ''} and unit in PACKAGE_UNITS:
        return f"{article} {str(_json_number(quantity)).replace('.', ',')} {unit}".strip()
    return article


def _parser_status(row: dict[str, Any]) -> str:
    if _raw_line(row) and _clean_line(row) and _line_price(row) not in {None, ''}:
        return 'diagnose_available'
    if _raw_line(row) or _clean_line(row):
        return 'needs_review'
    return 'unknown'


def _diagnosis_line(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'line_id': str(row.get('id') or ''),
        'line_index': int(row.get('line_index') or 0),
        'raw_line': _raw_line(row),
        'clean_line': _clean_line(row),
        'article_name': _article_name(row),
        'quantity_value': _json_number(_quantity_value(row)),
        'quantity_unit': _unit_value(row) or None,
        'package_size_label': _package_size_label(row),
        'line_price': _json_number(_line_price(row)),
        'unit_price': _json_number(row.get('display_unit_price') if row.get('display_unit_price') is not None else row.get('corrected_unit_price') if row.get('corrected_unit_price') is not None else row.get('unit_price')),
        'discount_amount': _json_number(row.get('discount_amount')),
        'barcode': _line_text(row, 'barcode') or None,
        'off_query': _off_query(row),
        'parser_status': _parser_status(row),
        'parser_confidence': _json_number(row.get('confidence_score')),
    }


def _receipt_where(include_inactive: bool) -> str:
    if include_inactive:
        return '1 = 1'
    return "COALESCE(rt.deleted_at, '') = '' AND COALESCE(rr.deleted_at, '') = ''"


def _receipt_index_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'receipt_table_id': str(row.get('receipt_table_id') or ''),
        'raw_receipt_id': str(row.get('raw_receipt_id') or ''),
        'household_id': str(row.get('household_id') or ''),
        'store_name': row.get('store_name'),
        'purchase_at': str(row.get('purchase_at')) if row.get('purchase_at') is not None else None,
        'total_amount': _json_number(row.get('total_amount')),
        'parse_status': row.get('parse_status'),
        'line_count': _json_number(row.get('line_count')),
        'created_at': str(row.get('created_at')) if row.get('created_at') is not None else None,
        'original_filename': row.get('original_filename'),
    }


def build_parse_quality_diagnosis(receipt_table_id: str, household_id: str | None = None, include_inactive: bool = False) -> dict[str, Any]:
    normalized_household_id = str(household_id or '').strip()
    where_parts = ['rt.id = :receipt_table_id', _receipt_where(include_inactive)]
    params = {'receipt_table_id': str(receipt_table_id or '').strip()}
    if normalized_household_id:
        where_parts.append('rt.household_id = :household_id')
        params['household_id'] = normalized_household_id
    with engine.begin() as conn:
        receipt = conn.execute(
            text(
                f"""
                SELECT
                    rt.id,
                    rt.raw_receipt_id,
                    rt.household_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.line_count,
                    rt.created_at,
                    rt.updated_at,
                    rr.original_filename,
                    rr.mime_type
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
        if not receipt:
            raise HTTPException(status_code=404, detail='Kassabon niet gevonden voor parsekwaliteit-diagnose')
        lines = conn.execute(
            text(
                """
                SELECT
                    id,
                    line_index,
                    raw_label,
                    normalized_label,
                    quantity,
                    unit,
                    unit_price,
                    line_total,
                    discount_amount,
                    barcode,
                    confidence_score
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, id ASC
                """
            ),
            {'receipt_table_id': str(receipt_table_id)},
        ).mappings().all()
    diagnosis_lines = [_diagnosis_line(dict(row)) for row in lines]
    return {
        'ok': True,
        'diagnosis_type': 'kassa_parse_quality',
        'receipt_id': str(receipt['id']),
        'receipt_table_id': str(receipt['id']),
        'raw_receipt_id': str(receipt['raw_receipt_id']),
        'household_id': str(receipt['household_id']),
        'store_name': receipt.get('store_name'),
        'store_branch': receipt.get('store_branch'),
        'purchase_at': str(receipt.get('purchase_at')) if receipt.get('purchase_at') is not None else None,
        'total_amount': _json_number(receipt.get('total_amount')),
        'currency': receipt.get('currency') or 'EUR',
        'parse_status': receipt.get('parse_status'),
        'parser_confidence': _json_number(receipt.get('confidence_score')),
        'original_filename': receipt.get('original_filename'),
        'mime_type': receipt.get('mime_type'),
        'line_count': len(diagnosis_lines),
        'mutates_inventory': False,
        'creates_inventory_event': False,
        'creates_product_group_assignment': False,
        'creates_catalog_link': False,
        'lines': diagnosis_lines,
    }


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


@router.get('/receipts/parse-quality-diagnosis/index')
def receipt_parse_quality_diagnosis_index(householdId: str | None = None, limit: int = 25, includeInactive: bool = False):
    """Read-only index met beschikbare kassabonnen voor parsekwaliteit-diagnose."""
    normalized_household_id = str(householdId or '').strip()
    where_parts = [_receipt_where(includeInactive)]
    params: dict[str, Any] = {'limit': max(1, min(int(limit or 25), 100))}
    if normalized_household_id:
        where_parts.append('rt.household_id = :household_id')
        params['household_id'] = normalized_household_id
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.household_id,
                    rt.store_name,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.parse_status,
                    rt.line_count,
                    rt.created_at,
                    rr.original_filename
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                ORDER BY datetime(rt.created_at) DESC, rt.id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return {
        'ok': True,
        'diagnosis_type': 'kassa_parse_quality_index',
        'household_id_filter': normalized_household_id or None,
        'include_inactive': bool(includeInactive),
        'count': len(rows),
        'mutates_inventory': False,
        'creates_inventory_event': False,
        'creates_product_group_assignment': False,
        'creates_catalog_link': False,
        'receipts': [_receipt_index_row(dict(row)) for row in rows],
    }


@router.get('/receipts/{receipt_table_id}/parse-quality-diagnosis')
def receipt_parse_quality_diagnosis(receipt_table_id: str, householdId: str | None = None, includeInactive: bool = False):
    """Read-only Kassa parsekwaliteit-diagnose per kassabon.

    Swagger/API-first endpoint voor kwaliteitsverbetering van het inleesproces.
    Het endpoint schrijft niets, koppelt niets, wijst geen productgroep toe en
    muteert geen voorraad.
    """
    return build_parse_quality_diagnosis(receipt_table_id, household_id=householdId, include_inactive=includeInactive)


@router.get('/receipts/latest/parse-quality-diagnosis')
def latest_receipt_parse_quality_diagnosis(householdId: str | None = None, includeInactive: bool = False):
    """Read-only parsekwaliteit-diagnose voor de meest recente beschikbare kassabon."""
    index_payload = receipt_parse_quality_diagnosis_index(householdId=householdId, limit=1, includeInactive=includeInactive)
    receipts = index_payload.get('receipts') or []
    if not receipts and householdId:
        index_payload = receipt_parse_quality_diagnosis_index(householdId=None, limit=1, includeInactive=includeInactive)
        receipts = index_payload.get('receipts') or []
    if not receipts and not includeInactive:
        index_payload = receipt_parse_quality_diagnosis_index(householdId=householdId, limit=1, includeInactive=True)
        receipts = index_payload.get('receipts') or []
    if not receipts:
        raise HTTPException(status_code=404, detail='Geen kassabon gevonden voor parsekwaliteit-diagnose')
    selected = receipts[0]
    diagnosis = build_parse_quality_diagnosis(
        str(selected['receipt_table_id']),
        household_id=str(selected.get('household_id') or '') or None,
        include_inactive=True,
    )
    diagnosis['selection'] = {
        'mode': 'latest_available_receipt',
        'requested_household_id': str(householdId or '').strip() or None,
        'selected_receipt_table_id': selected['receipt_table_id'],
    }
    return diagnosis


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
