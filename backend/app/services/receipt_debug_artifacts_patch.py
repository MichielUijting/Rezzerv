from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.debug_artifact_store import persist_ingest_debug_artifact
from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
_ORIGINAL_INGEST_RECEIPT = _receipt_service.ingest_receipt


def _load_stored_receipt_envelope(engine: Any, receipt_table_id: str) -> dict[str, Any]:
    if engine is None or not receipt_table_id:
        return {}
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        parse_status,
                        total_amount,
                        store_name,
                        line_count,
                        updated_at
                    FROM receipt_tables
                    WHERE id = :receipt_table_id
                    LIMIT 1
                    """
                ),
                {'receipt_table_id': receipt_table_id},
            ).mappings().first()
        return dict(row or {})
    except Exception as exc:
        return {'stored_receipt_lookup_error': str(exc)}


def ingest_receipt(*args: Any, **kwargs: Any):
    result = _ORIGINAL_INGEST_RECEIPT(*args, **kwargs)
    try:
        if not isinstance(result, dict):
            LOGGER.info('receipt_upload_response result_type=%s', type(result).__name__)
            return result
        receipt_table_id = result.get('receipt_table_id')
        raw_receipt_id = result.get('raw_receipt_id')
        engine = kwargs.get('engine') if 'engine' in kwargs else (args[0] if len(args) >= 1 else None)
        receipt_storage_root = kwargs.get('receipt_storage_root') if 'receipt_storage_root' in kwargs else (args[1] if len(args) >= 2 else None)
        household_id = kwargs.get('household_id') if 'household_id' in kwargs else (args[2] if len(args) >= 3 else None)
        filename = kwargs.get('filename') if 'filename' in kwargs else (args[3] if len(args) >= 4 else None)
        mime_type = kwargs.get('mime_type')
        stored = _load_stored_receipt_envelope(engine, str(receipt_table_id or ''))
        debug_artifact_persisted = False
        debug_artifact_error = None
        parser_debug = result.get('parser_debug') if isinstance(result.get('parser_debug'), dict) else None
        if receipt_table_id and raw_receipt_id and engine is not None and receipt_storage_root is not None:
            try:
                path = persist_ingest_debug_artifact(
                    engine=engine,
                    receipt_storage_root=Path(receipt_storage_root),
                    receipt_table_id=str(receipt_table_id),
                    raw_receipt_id=str(raw_receipt_id),
                    household_id=str(household_id or ''),
                    parse_result=None,
                    source_context={
                        'route': 'ingest_receipt_upload_flow',
                        'original_filename': filename,
                        'mime_type': mime_type,
                        'include_debug': bool(kwargs.get('include_debug')),
                        'parser_debug_available_in_response': bool(parser_debug),
                    },
                )
                debug_artifact_persisted = path is not None
                if path is not None:
                    result['debug_artifact_persisted'] = True
                    result['debug_artifact_path'] = str(path)
            except Exception as exc:
                debug_artifact_error = str(exc)
                result['debug_artifact_persisted'] = False
                result['debug_artifact_error'] = debug_artifact_error
        LOGGER.info(
            'receipt_upload_response receipt_table_id=%s raw_receipt_id=%s filename=%s response_parse_status=%s stored_parse_status=%s stored_total_amount=%s stored_store_name=%s stored_line_count=%s debug_artifact_persisted=%s debug_artifact_error=%s parser_debug_in_response=%s',
            receipt_table_id,
            raw_receipt_id,
            filename,
            result.get('parse_status'),
            stored.get('parse_status'),
            stored.get('total_amount'),
            stored.get('store_name'),
            stored.get('line_count'),
            debug_artifact_persisted,
            debug_artifact_error,
            bool(parser_debug),
        )
    except Exception as exc:
        LOGGER.warning('receipt_upload_response_logging_failed error=%s', exc)
    return result


_receipt_service.ingest_receipt = ingest_receipt
