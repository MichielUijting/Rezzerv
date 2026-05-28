from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.receipt_ingestion.debug_artifact_store import persist_ingest_debug_artifact
from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
_ORIGINAL_INGEST_RECEIPT = _receipt_service.ingest_receipt


def ingest_receipt(*args: Any, **kwargs: Any):
    result = _ORIGINAL_INGEST_RECEIPT(*args, **kwargs)
    try:
        if not isinstance(result, dict):
            return result
        receipt_table_id = result.get('receipt_table_id')
        raw_receipt_id = result.get('raw_receipt_id')
        if not receipt_table_id or not raw_receipt_id:
            return result
        engine = kwargs.get('engine') if 'engine' in kwargs else (args[0] if len(args) >= 1 else None)
        receipt_storage_root = kwargs.get('receipt_storage_root') if 'receipt_storage_root' in kwargs else (args[1] if len(args) >= 2 else None)
        household_id = kwargs.get('household_id') if 'household_id' in kwargs else (args[2] if len(args) >= 3 else None)
        filename = kwargs.get('filename') if 'filename' in kwargs else (args[3] if len(args) >= 4 else None)
        mime_type = kwargs.get('mime_type')
        include_debug = bool(kwargs.get('include_debug'))
        parse_result = None
        parser_debug = result.get('parser_debug') if isinstance(result.get('parser_debug'), dict) else None
        source_context = {
            'route': 'ingest_receipt_upload_flow',
            'original_filename': filename,
            'mime_type': mime_type,
            'include_debug': include_debug,
            'parser_debug_available_in_response': bool(parser_debug),
        }
        if parser_debug:
            source_context['parser_debug'] = parser_debug
        if engine is not None and receipt_storage_root is not None:
            path = persist_ingest_debug_artifact(
                engine=engine,
                receipt_storage_root=Path(receipt_storage_root),
                receipt_table_id=str(receipt_table_id),
                raw_receipt_id=str(raw_receipt_id),
                household_id=str(household_id or ''),
                parse_result=parse_result,
                source_context=source_context,
            )
            if path is not None:
                result['debug_artifact_persisted'] = True
                result['debug_artifact_path'] = str(path)
    except Exception as exc:
        LOGGER.warning('receipt_debug_artifact_persist_failed error=%s', exc)
        if isinstance(result, dict):
            result['debug_artifact_persisted'] = False
            result['debug_artifact_error'] = str(exc)
    return result


_receipt_service.ingest_receipt = ingest_receipt
