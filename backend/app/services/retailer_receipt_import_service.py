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
from app.services.receipt_service import ingest_receipt, reparse_receipt

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
        provider=envelope.provider,
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



def _refresh_existing_retailer_receipt_if_safe(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    household_id: str,
    source_id: str | None,
    filename: str,
    file_bytes: bytes,
    duplicate_result: dict[str, Any],
) -> dict[str, Any] | None:
    raw_receipt_id = str(duplicate_result.get("raw_receipt_id") or "").strip()
    receipt_table_id = str(duplicate_result.get("receipt_table_id") or "").strip()
    if not raw_receipt_id or not receipt_table_id:
        return None

    digest = hashlib.sha256(file_bytes).hexdigest()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    rr.id AS raw_receipt_id,
                    rr.source_id,
                    rr.original_filename,
                    rr.storage_path,
                    rr.deleted_at AS raw_deleted_at,
                    rt.id AS receipt_table_id,
                    rt.approved_at,
                    rt.workflow_state,
                    rt.deleted_at AS receipt_deleted_at,
                    EXISTS (
                        SELECT 1
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND (
                              COALESCE(rtl.is_validated, FALSE) = TRUE
                              OR rtl.corrected_raw_label IS NOT NULL
                              OR rtl.corrected_line_total IS NOT NULL
                          )
                    ) AS has_user_line_edits
                FROM raw_receipts rr
                JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
                WHERE rr.id = :raw_receipt_id
                  AND rt.id = :receipt_table_id
                  AND rr.household_id = :household_id
                  AND rt.household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "raw_receipt_id": raw_receipt_id,
                "receipt_table_id": receipt_table_id,
                "household_id": str(household_id),
            },
        ).mappings().first()
        if not row:
            return None

        workflow_state = str(row.get("workflow_state") or "active").strip().lower()
        if (
            row.get("raw_deleted_at") is not None
            or row.get("receipt_deleted_at") is not None
            or row.get("approved_at") is not None
            or bool(row.get("has_user_line_edits"))
            or workflow_state not in {"active", "returned_to_kassa"}
            or str(row.get("source_id") or "") != str(source_id or "")
            or str(row.get("original_filename") or "") != filename
        ):
            return None

        hash_conflict = conn.execute(
            text(
                """
                SELECT 1
                FROM raw_receipts
                WHERE household_id = :household_id
                  AND sha256_hash = :sha256_hash
                  AND id <> :raw_receipt_id
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {
                "household_id": str(household_id),
                "sha256_hash": digest,
                "raw_receipt_id": raw_receipt_id,
            },
        ).first()
        if hash_conflict:
            return None

    storage_path = Path(str(row.get("storage_path") or ""))
    try:
        storage_path.resolve().relative_to(receipt_storage_root.resolve())
    except Exception:
        return None
    if not storage_path.exists() or not storage_path.is_file():
        return None

    old_bytes = storage_path.read_bytes()
    temp_path = storage_path.with_suffix(storage_path.suffix + ".refresh.tmp")
    temp_path.write_bytes(file_bytes)
    temp_path.replace(storage_path)

    try:
        reparsed = reparse_receipt(
            engine,
            receipt_storage_root,
            receipt_table_id,
        )
        if not reparsed or reparsed.get("deleted"):
            raise RuntimeError("Bestaande retailerbon kon niet veilig worden herparsed")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE raw_receipts
                    SET sha256_hash = :sha256_hash,
                        mime_type = :mime_type,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :raw_receipt_id
                      AND household_id = :household_id
                    """
                ),
                {
                    "sha256_hash": digest,
                    "mime_type": RETAILER_RECEIPT_MIME,
                    "raw_receipt_id": raw_receipt_id,
                    "household_id": str(household_id),
                },
            )
    except Exception:
        restore_path = storage_path.with_suffix(storage_path.suffix + ".restore.tmp")
        restore_path.write_bytes(old_bytes)
        restore_path.replace(storage_path)
        raise

    return {
        **duplicate_result,
        "refreshed_existing_receipt": True,
        "parse_status": reparsed.get("parse_status"),
        "line_count": reparsed.get("line_count"),
    }

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
    if result.get("duplicate"):
        refreshed = _refresh_existing_retailer_receipt_if_safe(
            engine,
            receipt_storage_root,
            household_id=household_id,
            source_id=source.get("id"),
            filename=filename,
            file_bytes=file_bytes,
            duplicate_result=result,
        )
        if refreshed is not None:
            result = refreshed
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
