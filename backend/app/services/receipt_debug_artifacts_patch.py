from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.debug_artifact_store import persist_ingest_debug_artifact
from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
_ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES = _receipt_service._parse_result_from_text_lines
_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content
_ORIGINAL_INGEST_RECEIPT = _receipt_service.ingest_receipt
_LAST_PARSE_CAPTURE: dict[str, Any] = {}


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


def _capture_source_lines(result: Any, text_lines: list[str], filename: str, parser_kwargs: dict[str, Any]) -> Any:
    source_lines = list(text_lines or [])
    try:
        setattr(result, '_rezzerv_source_lines', source_lines)
        setattr(result, '_rezzerv_merged_lines', [])
        setattr(result, '_rezzerv_parser_input_filename', filename)
        setattr(result, '_rezzerv_parser_input_kwargs', dict(parser_kwargs or {}))
    except Exception:
        # Debug metadata must never change parsing behavior.
        pass
    try:
        diagnostics = dict(getattr(result, 'parser_diagnostics', None) or {})
        diagnostics.setdefault('ingest_debug_source', {
            'source': 'active_parse_result_from_text_lines',
            'filename': filename,
            'source_line_count': len(source_lines),
            'parser_kwargs': dict(parser_kwargs or {}),
        })
        result.parser_diagnostics = diagnostics
    except Exception:
        pass
    return result


def _parse_result_from_text_lines_with_debug_capture(text_lines: list[str], filename: str, **kwargs: Any):
    result = _ORIGINAL_PARSE_RESULT_FROM_TEXT_LINES(text_lines, filename, **kwargs)
    return _capture_source_lines(result, text_lines, filename, kwargs)


def parse_receipt_content(*args: Any, **kwargs: Any):
    global _LAST_PARSE_CAPTURE
    _LAST_PARSE_CAPTURE = {}
    result = _ORIGINAL_PARSE_RECEIPT_CONTENT(*args, **kwargs)
    source_lines = list(getattr(result, '_rezzerv_source_lines', []) or []) if result is not None else []
    merged_lines = list(getattr(result, '_rezzerv_merged_lines', []) or []) if result is not None else []
    _LAST_PARSE_CAPTURE = {
        'parse_result': result,
        'source_lines': source_lines,
        'merged_lines': merged_lines,
        'parser_input_filename': getattr(result, '_rezzerv_parser_input_filename', None) if result is not None else None,
        'parser_input_kwargs': getattr(result, '_rezzerv_parser_input_kwargs', {}) if result is not None else {},
        'parse_result_available': result is not None,
    }
    return result


def _latest_parse_capture() -> dict[str, Any]:
    return dict(_LAST_PARSE_CAPTURE or {})


def ingest_receipt(*args: Any, **kwargs: Any):
    global _LAST_PARSE_CAPTURE
    _LAST_PARSE_CAPTURE = {}
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
        capture = _latest_parse_capture()
        parse_result = capture.get('parse_result')
        source_lines = list(capture.get('source_lines') or [])
        merged_lines = list(capture.get('merged_lines') or [])

        # Duplicate responses do not represent a fresh ingest run. Avoid overwriting
        # an existing persisted artifact with an empty duplicate snapshot.
        if result.get('duplicate'):
            LOGGER.info(
                'receipt_upload_response receipt_table_id=%s raw_receipt_id=%s filename=%s duplicate=True response_parse_status=%s stored_parse_status=%s stored_total_amount=%s stored_store_name=%s stored_line_count=%s parser_debug_in_response=%s',
                receipt_table_id,
                raw_receipt_id,
                filename,
                result.get('parse_status'),
                stored.get('parse_status'),
                stored.get('total_amount'),
                stored.get('store_name'),
                stored.get('line_count'),
                bool(parser_debug),
            )
            return result

        if receipt_table_id and raw_receipt_id and engine is not None and receipt_storage_root is not None:
            try:
                path = persist_ingest_debug_artifact(
                    engine=engine,
                    receipt_storage_root=Path(receipt_storage_root),
                    receipt_table_id=str(receipt_table_id),
                    raw_receipt_id=str(raw_receipt_id),
                    household_id=str(household_id or ''),
                    parse_result=parse_result,
                    source_context={
                        'route': 'ingest_receipt_upload_flow_parse_capture',
                        'original_filename': filename,
                        'mime_type': mime_type,
                        'include_debug': bool(kwargs.get('include_debug')),
                        'parser_debug_available_in_response': bool(parser_debug),
                        'parse_result_available': parse_result is not None,
                        'parser_input_filename': capture.get('parser_input_filename'),
                        'parser_input_kwargs': capture.get('parser_input_kwargs') or {},
                        'source_lines': source_lines,
                        'merged_lines': merged_lines,
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
            'receipt_upload_response receipt_table_id=%s raw_receipt_id=%s filename=%s response_parse_status=%s stored_parse_status=%s stored_total_amount=%s stored_store_name=%s stored_line_count=%s debug_artifact_persisted=%s debug_artifact_error=%s parse_result_captured=%s source_line_count=%s parser_debug_in_response=%s',
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
            parse_result is not None,
            len(source_lines),
            bool(parser_debug),
        )
    except Exception as exc:
        LOGGER.warning('receipt_upload_response_logging_failed error=%s', exc)
    finally:
        _LAST_PARSE_CAPTURE = {}
    return result


_receipt_service._parse_result_from_text_lines = _parse_result_from_text_lines_with_debug_capture
_receipt_service.parse_receipt_content = parse_receipt_content
_receipt_service.ingest_receipt = ingest_receipt
