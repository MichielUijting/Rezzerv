from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services import receipt_service as _receipt_service
from app.services.receipt_status_baseline_service import validate_receipt_status_baseline

_ORIGINAL_INGEST_RECEIPT = _receipt_service.ingest_receipt
_ORIGINAL_REPARSE_RECEIPT = _receipt_service.reparse_receipt


def _sync_statuses_from_central_baseline_service(engine: Any, household_id: str | None = None) -> None:
    """Single source of truth for receipt category assignment.

    Parser/reparser only extract facts. The visible category in receipt_tables.parse_status
    is assigned by receipt_status_baseline_service_v4 through validate_receipt_status_baseline.
    """
    with engine.begin() as conn:
        validate_receipt_status_baseline(conn, household_id=household_id)


def _refresh_result_parse_status(engine: Any, result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return result
    receipt_table_id = str(result.get('receipt_table_id') or '').strip()
    if not receipt_table_id:
        return result
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT parse_status FROM receipt_tables WHERE id = :id LIMIT 1'),
            {'id': receipt_table_id},
        ).mappings().first()
    if row and row.get('parse_status'):
        result = dict(result)
        result['parse_status'] = row.get('parse_status')
    return result


def ingest_receipt(engine, receipt_storage_root, household_id, filename, file_bytes, source_id=None, mime_type=None, reject_non_receipt=False, create_failed_receipt_table=False, failed_store_name=None, failed_purchase_at=None):
    result = _ORIGINAL_INGEST_RECEIPT(
        engine,
        receipt_storage_root,
        household_id,
        filename,
        file_bytes,
        source_id=source_id,
        mime_type=mime_type,
        reject_non_receipt=reject_non_receipt,
        create_failed_receipt_table=create_failed_receipt_table,
        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
    )
    _sync_statuses_from_central_baseline_service(engine, household_id=str(household_id) if household_id is not None else None)
    return _refresh_result_parse_status(engine, result)


def reparse_receipt(engine, receipt_storage_root, receipt_table_id):
    result = _ORIGINAL_REPARSE_RECEIPT(engine, receipt_storage_root, receipt_table_id)
    household_id = None
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT household_id FROM receipt_tables WHERE id = :id LIMIT 1'),
            {'id': str(receipt_table_id)},
        ).mappings().first()
        if row:
            household_id = str(row.get('household_id') or '') or None
    _sync_statuses_from_central_baseline_service(engine, household_id=household_id)
    return _refresh_result_parse_status(engine, result)


def install_central_status_patch(main_module: Any | None = None) -> bool:
    if getattr(_receipt_service, '_rezzerv_central_receipt_status_patch_installed', False):
        if main_module is not None:
            main_module.ingest_receipt = _receipt_service.ingest_receipt
            main_module.reparse_receipt = _receipt_service.reparse_receipt
        return False

    _receipt_service.ingest_receipt = ingest_receipt
    _receipt_service.reparse_receipt = reparse_receipt
    _receipt_service._rezzerv_central_receipt_status_patch_installed = True

    if main_module is not None:
        main_module.ingest_receipt = ingest_receipt
        main_module.reparse_receipt = reparse_receipt

    return True
