from __future__ import annotations

import io
import traceback
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from app.services.receipt_service import detect_mime_type, parse_receipt_content

router = APIRouter(
    prefix='/api/receipt-import-diagnosis',
    tags=['receipt-import-diagnosis'],
)

SUPPORTED_DIAG_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.html', '.htm', '.txt', '.eml', '.webp'}


@router.get('/health')
def get_receipt_import_diagnosis_health() -> dict[str, Any]:
    return {
        'status': 'available',
        'diagnostic_only': True,
        'no_db_write': True,
    }


@router.post('/zip-dry-run')
async def diagnose_receipt_zip_import(file: UploadFile = File(...)) -> dict[str, Any]:
    """Read-only import diagnosis for a supermarket receipt ZIP.

    This endpoint does not call ingest_receipt and does not write to the DB.
    It explains per file whether the import pipeline can read, type-detect and
    parse the file enough to create a Kassa receipt, or where it fails.
    """
    filename = str(file.filename or 'upload.zip')
    content = await file.read()
    items: list[dict[str, Any]] = []

    if not zipfile.is_zipfile(io.BytesIO(content)):
        return {
            'filename': filename,
            'diagnostic_only': True,
            'no_db_write': True,
            'import_result': 'failed',
            'failure_stage': 'file_extract',
            'failure_reason': 'Upload is geen geldig ZIP-bestand.',
            'items': [],
            'summary': {
                'files_seen': 0,
                'would_create_receipt_table': 0,
                'should_be_manual': 0,
                'technical_failures': 1,
            },
        }

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            item_name = Path(member.filename).name
            suffix = Path(item_name).suffix.lower()
            if not item_name or item_name.startswith('__MACOSX'):
                continue
            if suffix not in SUPPORTED_DIAG_EXTENSIONS:
                items.append(_failed_item(item_name, 'mime_detect', f'Bestandstype {suffix or "zonder extensie"} wordt niet ondersteund.'))
                continue
            try:
                file_bytes = archive.read(member)
            except Exception as exc:
                items.append(_failed_item(
                    item_name,
                    'file_extract',
                    f'Bestand kon niet uit ZIP worden gelezen: {exc}',
                    exc=exc,
                    traceback_text=traceback.format_exc(),
                ))
                continue
            items.append(_diagnose_single_file(item_name, file_bytes))

    summary = _summarize(items)
    return {
        'filename': filename,
        'diagnostic_only': True,
        'no_db_write': True,
        'expected_behavior_policy': 'Technisch leesbare supermarktbonnen moeten zichtbaar worden in Kassa als Gecontroleerd, Controle nodig of Handmatig. Alleen corrupte/unsupported bestanden horen technisch mislukt te zijn.',
        'summary': summary,
        'items': items,
    }


def _diagnose_single_file(filename: str, file_bytes: bytes) -> dict[str, Any]:
    try:
        mime_type = detect_mime_type(filename, file_bytes)
    except Exception as exc:
        return _failed_item(
            filename,
            'mime_detect',
            f'MIME-detectie faalde: {exc}',
            exc=exc,
            traceback_text=traceback.format_exc(),
        )

    try:
        parse_result = parse_receipt_content(file_bytes, filename, mime_type)
    except Exception as exc:
        return {
            'filename': filename,
            'import_result': 'failed',
            'receipt_table_created': False,
            'raw_receipt_created': False,
            'failure_stage': 'parse',
            'failure_reason': f'Parser/OCR exception: {type(exc).__name__}: {exc}',
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
            'exception_traceback': traceback.format_exc(),
            'mime_type': mime_type,
            'expected_behavior': 'Parserfout moet worden hersteld; technisch leesbare supermarktbon mag niet verdwijnen.',
        }

    if not parse_result or not parse_result.is_receipt:
        return {
            'filename': filename,
            'import_result': 'failed',
            'receipt_table_created': False,
            'raw_receipt_created': True,
            'failure_stage': 'parse',
            'failure_reason': 'Parser classificeert dit bestand als geen bruikbare kassabon.',
            'exception_type': None,
            'exception_message': None,
            'exception_traceback': None,
            'mime_type': mime_type,
            'parse_status': getattr(parse_result, 'parse_status', None),
            'store_name': getattr(parse_result, 'store_name', None),
            'total_amount': _number_or_none(getattr(parse_result, 'total_amount', None)),
            'line_count': len(getattr(parse_result, 'lines', None) or []),
            'expected_behavior': 'Als dit een supermarktbon is, moet de importflow minimaal een Handmatig-bon aanmaken.',
        }

    line_count = len(parse_result.lines or [])
    total_amount = _number_or_none(parse_result.total_amount)
    has_store = bool(str(parse_result.store_name or '').strip())
    has_total = parse_result.total_amount is not None
    should_be_manual = not has_store or not has_total or line_count == 0

    return {
        'filename': filename,
        'import_result': 'would_create',
        'receipt_table_created': True,
        'raw_receipt_created': True,
        'failure_stage': None,
        'failure_reason': None,
        'exception_type': None,
        'exception_message': None,
        'exception_traceback': None,
        'mime_type': mime_type,
        'parse_status': parse_result.parse_status,
        'store_name': parse_result.store_name,
        'total_amount': total_amount,
        'line_count': line_count,
        'confidence_score': parse_result.confidence_score,
        'expected_behavior': 'create_manual_receipt_when_parse_quality_low' if should_be_manual else 'create_receipt_table_and_apply_existing_status_flow',
    }


def _failed_item(
    filename: str,
    stage: str,
    reason: str,
    *,
    exc: Exception | None = None,
    traceback_text: str | None = None,
) -> dict[str, Any]:
    return {
        'filename': filename,
        'import_result': 'failed',
        'receipt_table_created': False,
        'raw_receipt_created': False,
        'failure_stage': stage,
        'failure_reason': reason,
        'exception_type': type(exc).__name__ if exc else None,
        'exception_message': str(exc) if exc else None,
        'exception_traceback': traceback_text,
        'expected_behavior': 'technical_failure_only',
    }


def _summarize(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        'files_seen': len(items),
        'would_create_receipt_table': sum(1 for item in items if item.get('receipt_table_created') is True),
        'should_be_manual': sum(1 for item in items if item.get('expected_behavior') == 'create_manual_receipt_when_parse_quality_low'),
        'parse_failures': sum(1 for item in items if item.get('failure_stage') == 'parse'),
        'mime_or_extract_failures': sum(1 for item in items if item.get('failure_stage') in {'file_extract', 'mime_detect'}),
    }


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
