"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Household-scoped digital retailer receipt source and ingest service
- Runtime Type: production
- Used By: retailer receipt API routes
- Depends On: receipt_service.ingest_receipt
- Reads Data: yes
- Writes Data: yes
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.integrations.retailer_receipts import (
    RETAILER_RECEIPT_MIME,
    RetailerReceiptEnvelope,
)
from app.services.receipt_service import ingest_receipt

_PROVIDER_LABELS = {
    "ah": "Albert Heijn digitaal",
    "jumbo": "Jumbo digitaal",
    "lidl": "Lidl Plus digitaal",
}


def ensure_retailer_receipt_source(
    engine: Engine,
    *,
    household_id: str,
    provider: str,
) -> dict[str, Any]:
    source_id = f"{household_id}-retailer-{provider}"
    label = _PROVIDER_LABELS[provider]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_sources (
                    id, household_id, type, label, source_path, is_active
                ) VALUES (
                    :id, :household_id, 'retailer_api', :label, :source_path, TRUE
                )
                ON CONFLICT (id) DO UPDATE SET
                    household_id = EXCLUDED.household_id,
                    type = EXCLUDED.type,
                    label = EXCLUDED.label,
                    source_path = EXCLUDED.source_path,
                    is_active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "id": source_id,
                "household_id": str(household_id),
                "label": label,
                "source_path": provider,
            },
        )
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active,
                       last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE id = :id AND household_id = :household_id
                LIMIT 1
                """
            ),
            {"id": source_id, "household_id": str(household_id)},
        ).mappings().first()
    return dict(row or {})


_SOURCE_SNAPSHOT_KEY = "_sourceSnapshotDataUrl"
_MAX_SOURCE_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _decode_source_snapshot_data_url(value: Any) -> bytes | None:
    text_value = str(value or "").strip()
    prefix = "data:image/png;base64,"
    if not text_value.startswith(prefix):
        return None
    encoded = text_value[len(prefix):]
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not decoded or len(decoded) > _MAX_SOURCE_SNAPSHOT_BYTES:
        return None
    if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return decoded


def _sanitize_envelope_and_snapshot(
    envelope: RetailerReceiptEnvelope,
) -> tuple[RetailerReceiptEnvelope, bytes | None]:
    receipt_payload = dict(envelope.receipt or {})
    snapshot_bytes = _decode_source_snapshot_data_url(receipt_payload.pop(_SOURCE_SNAPSHOT_KEY, None))
    sanitized = RetailerReceiptEnvelope(
        schema_version=envelope.schema_version,
        provider=sanitized_envelope.provider,
        external_receipt_id=envelope.external_receipt_id,
        receipt=receipt_payload,
    )
    return sanitized, snapshot_bytes


def _source_preview_path(storage_path: Path) -> Path:
    return Path(str(storage_path) + ".source-preview.png")


def _store_source_preview(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    raw_receipt_id: str | None,
    snapshot_bytes: bytes | None,
) -> bool:
    if not raw_receipt_id or not snapshot_bytes:
        return False
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT storage_path
                FROM raw_receipts
                WHERE id = :raw_receipt_id
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"raw_receipt_id": str(raw_receipt_id)},
        ).mappings().first()
    if not row or not row.get("storage_path"):
        return False
    storage_path = Path(str(row["storage_path"]))
    try:
        storage_path.resolve().relative_to(receipt_storage_root.resolve())
    except Exception:
        return False
    preview_path = _source_preview_path(storage_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = preview_path.with_suffix(preview_path.suffix + ".tmp")
    temp_path.write_bytes(snapshot_bytes)
    temp_path.replace(preview_path)
    return True


def _stable_envelope_bytes(envelope: RetailerReceiptEnvelope) -> bytes:
    return json.dumps(
        envelope.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_external_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return normalized.strip(".-_")[:96] or hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]


def import_retailer_receipt(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    household_id: str,
    envelope: RetailerReceiptEnvelope,
) -> dict[str, Any]:
    sanitized_envelope, snapshot_bytes = _sanitize_envelope_and_snapshot(envelope)
    source = ensure_retailer_receipt_source(
        engine,
        household_id=household_id,
        provider=envelope.provider,
    )
    file_bytes = _stable_envelope_bytes(sanitized_envelope)
    filename = f"{sanitized_envelope.provider}-{_safe_external_id(sanitized_envelope.external_receipt_id)}.inhuis-receipt.json"
    result = ingest_receipt(
        engine,
        receipt_storage_root,
        household_id,
        filename,
        file_bytes,
        source_id=source.get("id"),
        mime_type=RETAILER_RECEIPT_MIME,
        reject_non_receipt=True,
    )
    preview_stored = _store_source_preview(
        engine,
        receipt_storage_root,
        raw_receipt_id=result.get("raw_receipt_id"),
        snapshot_bytes=snapshot_bytes,
    )
    return {
        **result,
        "provider": sanitized_envelope.provider,
        "external_receipt_id": sanitized_envelope.external_receipt_id,
        "source_id": source.get("id"),
        "source_preview_stored": preview_stored,
    }
