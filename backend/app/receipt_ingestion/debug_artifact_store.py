"""Persisted ingest-debug artifacts for receipt parsing.

Debug downloads must read stored JSON and must not run OCR, parse_receipt_content,
reparse_receipt, or any parser route.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

ARTIFACT_VERSION = 'R9-36D'


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _parse_result_payload(parse_result: Any | None) -> dict[str, Any] | None:
    if parse_result is None:
        return None
    lines = []
    for line in getattr(parse_result, 'lines', None) or []:
        lines.append(_json_safe(dict(line) if isinstance(line, dict) else line))
    return {
        'is_receipt': bool(getattr(parse_result, 'is_receipt', False)),
        'parse_status': getattr(parse_result, 'parse_status', None),
        'store_name': getattr(parse_result, 'store_name', None),
        'store_branch': getattr(parse_result, 'store_branch', None),
        'purchase_at': getattr(parse_result, 'purchase_at', None),
        'total_amount': _json_safe(getattr(parse_result, 'total_amount', None)),
        'discount_total': _json_safe(getattr(parse_result, 'discount_total', None)),
        'currency': getattr(parse_result, 'currency', None),
        'confidence_score': getattr(parse_result, 'confidence_score', None),
        'line_count': len(lines),
        'lines': lines,
    }


def _diagnostics_payload(parse_result: Any | None) -> dict[str, Any]:
    diagnostics = getattr(parse_result, 'parser_diagnostics', None) if parse_result is not None else None
    if isinstance(diagnostics, dict):
        return _json_safe(diagnostics)
    return {}


def _artifact_root(receipt_storage_root: Path) -> Path:
    configured = os.getenv('RECEIPT_DEBUG_ARTIFACT_ROOT', '').strip()
    if configured:
        return Path(configured)
    return Path(receipt_storage_root).parent / 'debug'


def _artifact_path(receipt_storage_root: Path, household_id: str, raw_receipt_id: str, imported_at: Any = None) -> Path:
    try:
        imported_dt = datetime.fromisoformat(str(imported_at).replace('Z', '+00:00')) if imported_at else datetime.now(timezone.utc)
    except Exception:
        imported_dt = datetime.now(timezone.utc)
    return _artifact_root(receipt_storage_root) / str(household_id) / imported_dt.strftime('%Y') / imported_dt.strftime('%m') / f'{raw_receipt_id}.json'


def _load_receipt_snapshot(engine: Any, receipt_table_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    with engine.begin() as conn:
        header = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.household_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.line_count,
                    rt.created_at,
                    rt.updated_at,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rr.sha256_hash,
                    rr.raw_status,
                    rr.imported_at
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.id = :receipt_table_id
                LIMIT 1
                """
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().first()
        if not header:
            return None, []
        lines = conn.execute(
            text(
                """
                SELECT
                    id,
                    line_index,
                    raw_label,
                    corrected_raw_label,
                    normalized_label,
                    quantity,
                    corrected_quantity,
                    unit,
                    corrected_unit,
                    unit_price,
                    corrected_unit_price,
                    line_total,
                    corrected_line_total,
                    discount_amount,
                    barcode,
                    article_match_status,
                    matched_article_id,
                    matched_global_product_id,
                    confidence_score,
                    COALESCE(is_deleted, 0) AS is_deleted,
                    COALESCE(is_validated, 0) AS is_validated,
                    created_at,
                    updated_at
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, created_at ASC
                """
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().all()
    return dict(header), [dict(line) for line in lines]


def build_ingest_debug_artifact(
    *,
    engine: Any,
    receipt_table_id: str,
    parse_result: Any | None = None,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_context = dict(source_context or {})
    header, lines = _load_receipt_snapshot(engine, receipt_table_id)
    now = datetime.now(timezone.utc).isoformat()
    if not header:
        return {
            'artifact_type': 'receipt_ingest_debug',
            'artifact_version': ARTIFACT_VERSION,
            'created_at': now,
            'receipt_table_id': receipt_table_id,
            'error': 'receipt_table_not_found',
        }
    source_lines = list(source_context.get('source_lines') or [])
    merged_lines = list(source_context.get('merged_lines') or [])
    return {
        'artifact_type': 'receipt_ingest_debug',
        'artifact_version': ARTIFACT_VERSION,
        'created_at': now,
        'raw_receipt_id': header.get('raw_receipt_id'),
        'receipt_table_id': header.get('receipt_table_id'),
        'original_filename': header.get('original_filename'),
        'mime_type': header.get('mime_type'),
        'storage_path': header.get('storage_path'),
        'sha256_hash': header.get('sha256_hash'),
        'raw_status': header.get('raw_status'),
        'imported_at': _json_safe(header.get('imported_at')),
        'source_context': _json_safe(source_context),
        'source_lines': {
            'count': len(source_lines),
            'lines': _json_safe(source_lines),
            'merged_count': len(merged_lines),
            'merged_lines': _json_safe(merged_lines),
        },
        'parse_result': _parse_result_payload(parse_result),
        'parser_diagnostics': _diagnostics_payload(parse_result),
        'stored_receipt': _json_safe(header),
        'stored_lines': _json_safe(lines),
        'debug_download_policy': {
            'persisted_at_ingest': parse_result is not None,
            'snapshot_from_stored_db': parse_result is None,
            'download_may_reparse': False,
            'download_may_run_ocr': False,
        },
    }


def persist_ingest_debug_artifact(
    *,
    engine: Any,
    receipt_storage_root: Path,
    receipt_table_id: str | None,
    raw_receipt_id: str | None,
    household_id: str | None,
    parse_result: Any | None = None,
    source_context: dict[str, Any] | None = None,
) -> Path | None:
    if not receipt_table_id or not raw_receipt_id or not household_id:
        return None
    artifact = build_ingest_debug_artifact(
        engine=engine,
        receipt_table_id=str(receipt_table_id),
        parse_result=parse_result,
        source_context=source_context,
    )
    imported_at = (artifact.get('stored_receipt') or {}).get('imported_at')
    path = _artifact_path(Path(receipt_storage_root), str(household_id), str(raw_receipt_id), imported_at=imported_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix('.json.tmp')
    tmp_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_path.replace(path)
    return path


def _latest_parser_capture_for_filename(original_filename: Any) -> tuple[Any | None, dict[str, Any]]:
    try:
        from app.services.receipt_parser_quality_patch import get_latest_ingest_debug_capture
        capture = get_latest_ingest_debug_capture()
    except Exception:
        return None, {}
    if not isinstance(capture, dict) or not capture:
        return None, {}
    capture_filename = str(capture.get('filename') or '').strip()
    wanted = str(original_filename or '').strip()
    if capture_filename and wanted and capture_filename != wanted:
        # Safe fallback: only attach in-memory parser capture when it clearly belongs
        # to the same upload filename.
        return None, {}
    return capture.get('parse_result'), {
        'route': 'latest_parser_capture_without_reparse',
        'original_filename': original_filename,
        'capture_filename': capture_filename,
        'source_lines': capture.get('source_lines') or [],
        'merged_lines': capture.get('merged_lines') or [],
        'note': 'Artifact gemaakt uit de laatst vastgelegde parsercapture; er is geen OCR of parser opnieuw uitgevoerd.',
    }


def read_ingest_debug_artifact_for_receipt(
    *,
    engine: Any,
    receipt_storage_root: Path,
    receipt_table_id: str,
) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.household_id,
                    rr.imported_at,
                    rr.original_filename
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.id = :receipt_table_id
                LIMIT 1
                """
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().first()
    if not row:
        return {
            'artifact_type': 'receipt_ingest_debug',
            'artifact_version': ARTIFACT_VERSION,
            'receipt_table_id': receipt_table_id,
            'available': False,
            'reason': 'receipt_table_not_found',
        }

    path = _artifact_path(
        Path(receipt_storage_root),
        str(row.get('household_id')),
        str(row.get('raw_receipt_id')),
        imported_at=row.get('imported_at'),
    )
    if not path.exists():
        parse_result, source_context = _latest_parser_capture_for_filename(row.get('original_filename'))
        if parse_result is None:
            source_context = {
                'route': 'stored_db_snapshot_without_reparse',
                'original_filename': row.get('original_filename'),
                'note': 'Artifact gemaakt uit opgeslagen databasevelden; er is geen OCR of parser opnieuw uitgevoerd.',
            }
        created_path = persist_ingest_debug_artifact(
            engine=engine,
            receipt_storage_root=Path(receipt_storage_root),
            receipt_table_id=str(row.get('receipt_table_id')),
            raw_receipt_id=str(row.get('raw_receipt_id')),
            household_id=str(row.get('household_id')),
            parse_result=parse_result,
            source_context=source_context,
        )
        if created_path is None or not created_path.exists():
            return {
                'artifact_type': 'receipt_ingest_debug',
                'artifact_version': ARTIFACT_VERSION,
                'receipt_table_id': str(row.get('receipt_table_id')),
                'raw_receipt_id': str(row.get('raw_receipt_id')),
                'original_filename': row.get('original_filename'),
                'available': False,
                'reason': 'missing_ingest_debug_artifact',
                'message': 'Geen ingest-debugartifact beschikbaar en snapshot kon niet worden aangemaakt. Downloaden voert bewust geen reparse/OCR uit.',
                'debug_download_policy': {
                    'persisted_at_ingest': False,
                    'download_may_reparse': False,
                    'download_may_run_ocr': False,
                },
            }
        path = created_path
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        return {
            'artifact_type': 'receipt_ingest_debug',
            'artifact_version': ARTIFACT_VERSION,
            'receipt_table_id': str(row.get('receipt_table_id')),
            'raw_receipt_id': str(row.get('raw_receipt_id')),
            'available': False,
            'reason': 'artifact_read_failed',
            'message': str(exc),
            'debug_download_policy': {
                'persisted_at_ingest': True,
                'download_may_reparse': False,
                'download_may_run_ocr': False,
            },
        }
    if isinstance(payload, dict):
        payload['available'] = True
        payload.setdefault('debug_download_policy', {
            'persisted_at_ingest': True,
            'download_may_reparse': False,
            'download_may_run_ocr': False,
        })
        return payload
    return {
        'artifact_type': 'receipt_ingest_debug',
        'artifact_version': ARTIFACT_VERSION,
        'receipt_table_id': str(row.get('receipt_table_id')),
        'raw_receipt_id': str(row.get('raw_receipt_id')),
        'available': False,
        'reason': 'artifact_payload_not_object',
        'debug_download_policy': {
            'persisted_at_ingest': True,
            'download_may_reparse': False,
            'download_may_run_ocr': False,
        },
    }
