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
    source = ensure_retailer_receipt_source(
        engine,
        household_id=household_id,
        provider=envelope.provider,
    )
    file_bytes = _stable_envelope_bytes(envelope)
    filename = f"{envelope.provider}-{_safe_external_id(envelope.external_receipt_id)}.inhuis-receipt.json"
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
    return {
        **result,
        "provider": envelope.provider,
        "external_receipt_id": envelope.external_receipt_id,
        "source_id": source.get("id"),
    }
