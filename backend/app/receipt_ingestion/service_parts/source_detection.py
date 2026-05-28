from __future__ import annotations

import hashlib
import mimetypes
import re
from typing import Any

from sqlalchemy import text

def sanitize_filename(name: str) -> str:
    candidate = (name or 'receipt').strip().replace('\\', '_').replace('/', '_')
    candidate = re.sub(r'[^A-Za-z0-9._ -]+', '_', candidate)
    candidate = candidate.strip(' ._') or 'receipt'
    return candidate[:180]


def sanitize_share_context(value: str | None) -> str:
    candidate = re.sub(r'[^a-z0-9_]+', '_', str(value or '').strip().lower())
    candidate = candidate.strip('_')
    return candidate or 'shared_file'


def share_source_label_for_context(context: str) -> str:
    mapping = {
        'shared_app': 'Gedeeld uit app',
        'shared_web': 'Gedeeld uit website',
        'shared_file': 'Gedeeld bestand',
        'shared_image': 'Gedeelde afbeelding',
        'shared_pdf': 'Gedeelde pdf',
    }
    return mapping.get(context, f"Gedeeld ({context.replace('_', ' ')})")


def ensure_share_receipt_source(engine, household_id: str, context: str) -> dict[str, Any]:
    normalized_context = sanitize_share_context(context)
    source_id = f'{household_id}-{normalized_context}'
    label = share_source_label_for_context(normalized_context)
    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at FROM receipt_sources WHERE id = :id LIMIT 1'),
            {'id': source_id},
        ).mappings().first()
        if row:
            conn.execute(
                text('UPDATE receipt_sources SET label = :label, type = :type, is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
                {'id': source_id, 'label': label, 'type': 'share_target'},
            )
        else:
            conn.execute(
                text(
                    'INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active) VALUES (:id, :household_id, :type, :label, NULL, 1)'
                ),
                {'id': source_id, 'household_id': household_id, 'type': 'share_target', 'label': label},
            )
        row = conn.execute(
            text('SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at FROM receipt_sources WHERE id = :id LIMIT 1'),
            {'id': source_id},
        ).mappings().first()
    return dict(row)


def detect_mime_type(filename: str, file_bytes: bytes, provided: str | None = None) -> str:
    if provided and provided != 'application/octet-stream':
        return provided
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if file_bytes.startswith(b'%PDF'):
        return 'application/pdf'
    if file_bytes.startswith(b'\x89PNG'):
        return 'image/png'
    if file_bytes.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WEBP':
        return 'image/webp'
    if file_bytes[:5].lower().startswith(b'from:') or b'content-type:' in file_bytes[:4096].lower():
        return 'message/rfc822'
    return 'application/octet-stream'


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
