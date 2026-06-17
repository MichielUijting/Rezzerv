from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine

LINK_TABLE_NAME = "external_receipt_item_links"

CREATE_EXTERNAL_RECEIPT_ITEM_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS external_receipt_item_links (
    id TEXT PRIMARY KEY,
    context_key TEXT NOT NULL,
    active_external_candidate_id TEXT,
    active_standard_product_id TEXT,
    link_status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

CREATE_CONTEXT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_external_receipt_item_links_context
ON external_receipt_item_links (context_key, link_status)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_external_receipt_item_link_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_RECEIPT_ITEM_LINKS_SQL))
        conn.execute(text(CREATE_CONTEXT_INDEX_SQL))


def set_active_external_receipt_item_link(
    context_key: str,
    candidate_id: str,
    standard_product_id: str | None = None,
    created_by: str = "external_databases_user_selection",
) -> dict[str, Any]:
    """Leg de enige actieve Externe-databases-koppeling voor een bonartikel vast."""
    ensure_external_receipt_item_link_schema()
    normalized_context_key = str(context_key or "").strip()
    normalized_candidate_id = str(candidate_id or "").strip()
    normalized_standard_product_id = str(standard_product_id or "").strip() or None

    if not normalized_context_key:
        return {"ok": False, "reason": "missing_context_key"}
    if not normalized_candidate_id:
        return {"ok": False, "reason": "missing_candidate_id"}

    timestamp = now_iso()
    link_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-external-link:{normalized_context_key}"))

    with engine.begin() as conn:
        dialect_name = str(engine.dialect.name or "").lower()
        params = {
            "id": link_id,
            "context_key": normalized_context_key,
            "active_external_candidate_id": normalized_candidate_id,
            "active_standard_product_id": normalized_standard_product_id,
            "link_status": "active",
            "created_by": created_by,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        if dialect_name == "sqlite":
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO external_receipt_item_links (
                        id,
                        context_key,
                        active_external_candidate_id,
                        active_standard_product_id,
                        link_status,
                        created_by,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :context_key,
                        :active_external_candidate_id,
                        :active_standard_product_id,
                        :link_status,
                        :created_by,
                        COALESCE((SELECT created_at FROM external_receipt_item_links WHERE id = :id), :created_at),
                        :updated_at
                    )
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO external_receipt_item_links (
                        id,
                        context_key,
                        active_external_candidate_id,
                        active_standard_product_id,
                        link_status,
                        created_by,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :context_key,
                        :active_external_candidate_id,
                        :active_standard_product_id,
                        :link_status,
                        :created_by,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        active_external_candidate_id = EXCLUDED.active_external_candidate_id,
                        active_standard_product_id = EXCLUDED.active_standard_product_id,
                        link_status = EXCLUDED.link_status,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                params,
            )

    return {
        "ok": True,
        "link_id": link_id,
        "context_key": normalized_context_key,
        "active_external_candidate_id": normalized_candidate_id,
        "active_standard_product_id": normalized_standard_product_id,
        "is_linked": True,
    }


def clear_active_external_receipt_item_links(context_keys: list[str] | None = None, candidate_ids: list[str] | None = None) -> dict[str, Any]:
    ensure_external_receipt_item_link_schema()
    normalized_context_keys = [str(value).strip() for value in (context_keys or []) if str(value).strip()]
    normalized_candidate_ids = [str(value).strip() for value in (candidate_ids or []) if str(value).strip()]

    if not normalized_context_keys and not normalized_candidate_ids:
        return {"ok": True, "cleared_count": 0}

    where_parts: list[str] = []
    params: dict[str, Any] = {"updated_at": now_iso()}

    if normalized_context_keys:
        keys = []
        for index, value in enumerate(normalized_context_keys):
            key = f"context_key_{index}"
            keys.append(f":{key}")
            params[key] = value
        where_parts.append(f"context_key IN ({', '.join(keys)})")

    if normalized_candidate_ids:
        keys = []
        for index, value in enumerate(normalized_candidate_ids):
            key = f"candidate_id_{index}"
            keys.append(f":{key}")
            params[key] = value
        where_parts.append(f"active_external_candidate_id IN ({', '.join(keys)})")

    where_sql = " OR ".join(where_parts)

    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE external_receipt_item_links
                SET link_status = 'inactive',
                    updated_at = :updated_at
                WHERE link_status = 'active'
                  AND ({where_sql})
                """
            ),
            params,
        )

    return {"ok": True, "cleared_count": int(result.rowcount or 0)}


def list_active_external_receipt_item_links(context_keys: list[str] | None = None) -> dict[str, dict[str, Any]]:
    ensure_external_receipt_item_link_schema()
    normalized_context_keys = [str(value).strip() for value in (context_keys or []) if str(value).strip()]

    params: dict[str, Any] = {}
    where_sql = "link_status = 'active'"
    if normalized_context_keys:
        keys = []
        for index, value in enumerate(normalized_context_keys):
            key = f"context_key_{index}"
            keys.append(f":{key}")
            params[key] = value
        where_sql += f" AND context_key IN ({', '.join(keys)})"

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM external_receipt_item_links
                WHERE {where_sql}
                """
            ),
            params,
        ).mappings().all()

    return {str(row.get("context_key") or ""): dict(row) for row in rows}
