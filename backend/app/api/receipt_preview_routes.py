from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Optional

import cv2
from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text

router = APIRouter(
    prefix="/api/receipts",
    tags=["receipt-preview"],
)

_engine = None
_receipt_storage_root: Path | None = None
_receipt_preview_normalizer = None
_require_entity_household_access: Callable | None = None


def configure_receipt_preview_routes(
    *,
    engine,
    receipt_storage_root: Path,
    receipt_preview_normalizer,
    require_entity_household_access: Callable,
) -> None:
    """Configure dependencies supplied by main.py during router activation.

    This keeps the module free of imports from app.main and avoids circular
    imports while preserving the existing endpoint contract.
    """
    global _engine, _receipt_storage_root, _receipt_preview_normalizer, _require_entity_household_access
    _engine = engine
    _receipt_storage_root = Path(receipt_storage_root)
    _receipt_preview_normalizer = receipt_preview_normalizer
    _require_entity_household_access = require_entity_household_access


def _require_configured() -> tuple[object, Path, object, Callable]:
    if _engine is None or _receipt_storage_root is None or _receipt_preview_normalizer is None or _require_entity_household_access is None:
        raise HTTPException(status_code=500, detail='Receipt preview router is niet geconfigureerd')
    return _engine, _receipt_storage_root, _receipt_preview_normalizer, _require_entity_household_access


def _generate_fallback_processed_preview(storage_path: Path) -> Path | None:
    try:
        image = cv2.imread(str(storage_path))
        if image is None:
            return None
        if image.shape[0] < image.shape[1]:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        temp_dir = Path(tempfile.mkdtemp(prefix='rezzerv_receipt_preview_'))
        output_path = temp_dir / 'processed_preview.png'
        cv2.imwrite(str(output_path), processed)
        return output_path
    except Exception:
        return None


@router.get('/{receipt_table_id}/preview')
def get_receipt_preview(receipt_table_id: str, variant: str = Query('original'), authorization: Optional[str] = Header(None)):
    engine, receipt_storage_root, receipt_preview_normalizer, require_entity_household_access = _require_configured()
    with engine.begin() as conn:
        require_entity_household_access(conn, 'receipt_tables', receipt_table_id, authorization, admin_only=False)
        record = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rem.body_html,
                    rem.body_text,
                    rem.selected_part_type
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.id = :receipt_table_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().first()
    if not record:
        raise HTTPException(status_code=404, detail='Bon niet gevonden')

    selected_part_type = str(record.get('selected_part_type') or '').strip().lower()
    body_html = record.get('body_html')
    body_text = record.get('body_text')
    variant_value = str(variant or 'original').strip().lower()

    if variant_value not in {'original', 'processed'}:
        raise HTTPException(status_code=400, detail='Onbekende previewvariant')

    if variant_value == 'original':
        if selected_part_type in {'html_body', 'text_body'} and body_html:
            return HTMLResponse(content=str(body_html), headers={'Content-Disposition': 'inline'})
        if selected_part_type == 'text_body' and body_text:
            return Response(content=str(body_text), media_type='text/plain', headers={'Content-Disposition': 'inline'})

    storage_path = Path(record['storage_path'] or '')
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(status_code=404, detail='Originele bon ontbreekt')

    try:
        storage_path.resolve().relative_to(receipt_storage_root.resolve())
    except Exception:
        raise HTTPException(status_code=403, detail='Bonbestand ligt buiten de toegestane opslag')

    mime_type = str(record['mime_type'] or 'application/octet-stream')
    filename = str(record['original_filename'] or storage_path.name)
    headers = {'Content-Disposition': f'inline; filename="{Path(filename).name}"'}

    if variant_value == 'processed':
        if not str(mime_type).lower().startswith('image/'):
            raise HTTPException(status_code=404, detail='Bewerkte bonpreview is niet beschikbaar voor dit bestandstype')
        normalized = receipt_preview_normalizer.normalize(str(storage_path), mime_type)
        processed_path = None
        if normalized.success and normalized.normalized_path and Path(normalized.normalized_path).exists():
            processed_path = Path(normalized.normalized_path)
        elif normalized.success and normalized.ocr_ready_path and Path(normalized.ocr_ready_path).exists():
            processed_path = Path(normalized.ocr_ready_path)
        if processed_path is None:
            processed_path = _generate_fallback_processed_preview(storage_path)
        if processed_path is None or not processed_path.exists():
            raise HTTPException(status_code=404, detail='Bewerkte bonpreview is niet beschikbaar')
        processed_name = f'{Path(filename).stem}-processed.png'
        return FileResponse(path=processed_path, media_type='image/png', filename=processed_name, headers={'Content-Disposition': f'inline; filename="{processed_name}"'})

    return FileResponse(path=storage_path, media_type=mime_type, filename=Path(filename).name, headers=headers)
