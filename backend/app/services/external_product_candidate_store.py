from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_database_matchers import match_retailer_receipt_line

PROTECTED_CANDIDATE_STATUSES = {
    "user_confirmed",
    "external_database_override",
}


CREATE_EXTERNAL_PRODUCT_CANDIDATES_SQL = """
CREATE TABLE IF NOT EXISTS external_product_candidates (
    id TEXT PRIMARY KEY,
    receipt_line_id TEXT,
    purchase_import_line_id TEXT,
    context_key TEXT NOT NULL,
    retailer_code TEXT NOT NULL,
    receipt_line_text TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    candidate_brand TEXT,
    candidate_source_name TEXT,
    candidate_source_product_code TEXT,
    retailer_article_number TEXT,
    quantity_label TEXT,
    variant TEXT,
    source_url TEXT,
    score REAL NOT NULL,
    score_breakdown_json TEXT,
    candidate_status TEXT NOT NULL,
    is_probable INTEGER NOT NULL DEFAULT 0,
    is_user_confirmed INTEGER NOT NULL DEFAULT 0,
    is_external_database_override INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_EXTERNAL_PRODUCT_CANDIDATES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_external_product_candidates_context
ON external_product_candidates (context_key, retailer_code, candidate_source_name, candidate_source_product_code, variant)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_candidate_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def build_candidate_context_key(retailer_code: str, receipt_line_text: str, receipt_line_id: str | None = None, purchase_import_line_id: str | None = None) -> str:
    if receipt_line_id:
        return f"receipt-line:{receipt_line_id}"
    if purchase_import_line_id:
        return f"purchase-import-line:{purchase_import_line_id}"
    return f"external-preview:{normalize_candidate_text(retailer_code)}:{normalize_candidate_text(receipt_line_text)}"


def ensure_external_product_candidates_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_CANDIDATES_SQL))
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_CANDIDATES_INDEX_SQL))


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "candidate_source_name": str(candidate.get("candidate_source_name") or "").strip(),
        "candidate_source_product_code": str(candidate.get("candidate_source_product_code") or candidate.get("retailer_article_number") or "").strip(),
        "variant": str(candidate.get("variant") or "").strip(),
        "candidate_name": str(candidate.get("candidate_name") or "").strip(),
    }


def _find_existing_candidate(conn, context_key: str, retailer_code: str, candidate: dict[str, Any]):
    identity = _candidate_identity(candidate)
    return conn.execute(
        text(
            """
            SELECT id, candidate_status, is_user_confirmed, is_external_database_override
            FROM external_product_candidates
            WHERE context_key = :context_key
              AND retailer_code = :retailer_code
              AND COALESCE(candidate_source_name, '') = COALESCE(:candidate_source_name, '')
              AND COALESCE(candidate_source_product_code, '') = COALESCE(:candidate_source_product_code, '')
              AND COALESCE(variant, '') = COALESCE(:variant, '')
              AND COALESCE(candidate_name, '') = COALESCE(:candidate_name, '')
            LIMIT 1
            """
        ),
        {
            "context_key": context_key,
            "retailer_code": retailer_code,
            **identity,
        },
    ).mappings().first()


def _is_protected(existing: dict[str, Any] | None) -> bool:
    if not existing:
        return False
    status = str(existing.get("candidate_status") or "").strip()
    return (
        status in PROTECTED_CANDIDATE_STATUSES
        or bool(existing.get("is_user_confirmed"))
        or bool(existing.get("is_external_database_override"))
    )


def _serialize_score_breakdown(candidate: dict[str, Any]) -> str:
    return json.dumps(candidate.get("score_breakdown") or {}, ensure_ascii=False, sort_keys=True)


def save_matchpreview_candidates(
    retailer_code: str,
    receipt_line_text: str,
    receipt_line_id: str | None = None,
    purchase_import_line_id: str | None = None,
    include_below_threshold: bool = False,
) -> dict[str, Any]:
    ensure_external_product_candidates_schema()

    match_result = match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    normalized_retailer = str(match_result.get("retailer_code") or retailer_code or "").strip().lower()
    context_key = build_candidate_context_key(
        normalized_retailer,
        receipt_line_text,
        receipt_line_id=receipt_line_id,
        purchase_import_line_id=purchase_import_line_id,
    )
    candidates = list(match_result.get("candidates") or [])
    timestamp = now_iso()
    saved = []
    skipped = []
    updated = []

    with engine.begin() as conn:
        for candidate in candidates:
            existing = _find_existing_candidate(conn, context_key, normalized_retailer, candidate)
            if _is_protected(existing):
                skipped.append({"id": existing.get("id"), "reason": "protected_candidate"})
                continue

            candidate_id = str(existing.get("id")) if existing else str(uuid.uuid4())
            params = {
                "id": candidate_id,
                "receipt_line_id": receipt_line_id,
                "purchase_import_line_id": purchase_import_line_id,
                "context_key": context_key,
                "retailer_code": normalized_retailer,
                "receipt_line_text": receipt_line_text,
                "candidate_name": str(candidate.get("candidate_name") or "").strip(),
                "candidate_brand": str(candidate.get("candidate_brand") or "").strip() or None,
                "candidate_source_name": str(candidate.get("candidate_source_name") or "").strip() or None,
                "candidate_source_product_code": str(candidate.get("candidate_source_product_code") or candidate.get("retailer_article_number") or "").strip() or None,
                "retailer_article_number": str(candidate.get("retailer_article_number") or "").strip() or None,
                "quantity_label": str(candidate.get("quantity_label") or "").strip() or None,
                "variant": str(candidate.get("variant") or "").strip() or None,
                "source_url": str(candidate.get("source_url") or "").strip() or None,
                "score": float(candidate.get("score") or 0),
                "score_breakdown_json": _serialize_score_breakdown(candidate),
                "candidate_status": str(candidate.get("candidate_status") or "possible_candidate").strip(),
                "is_probable": 1 if bool(candidate.get("is_probable")) else 0,
                "is_user_confirmed": 0,
                "is_external_database_override": 0,
                "created_by": str(candidate.get("created_by") or "external_database_matchpreview_save_v1").strip(),
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE external_product_candidates
                        SET receipt_line_id = :receipt_line_id,
                            purchase_import_line_id = :purchase_import_line_id,
                            receipt_line_text = :receipt_line_text,
                            candidate_brand = :candidate_brand,
                            candidate_source_name = :candidate_source_name,
                            candidate_source_product_code = :candidate_source_product_code,
                            retailer_article_number = :retailer_article_number,
                            quantity_label = :quantity_label,
                            source_url = :source_url,
                            score = :score,
                            score_breakdown_json = :score_breakdown_json,
                            candidate_status = :candidate_status,
                            is_probable = :is_probable,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    params,
                )
                updated.append(candidate_id)
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO external_product_candidates (
                            id,
                            receipt_line_id,
                            purchase_import_line_id,
                            context_key,
                            retailer_code,
                            receipt_line_text,
                            candidate_name,
                            candidate_brand,
                            candidate_source_name,
                            candidate_source_product_code,
                            retailer_article_number,
                            quantity_label,
                            variant,
                            source_url,
                            score,
                            score_breakdown_json,
                            candidate_status,
                            is_probable,
                            is_user_confirmed,
                            is_external_database_override,
                            created_by,
                            created_at,
                            updated_at
                        ) VALUES (
                            :id,
                            :receipt_line_id,
                            :purchase_import_line_id,
                            :context_key,
                            :retailer_code,
                            :receipt_line_text,
                            :candidate_name,
                            :candidate_brand,
                            :candidate_source_name,
                            :candidate_source_product_code,
                            :retailer_article_number,
                            :quantity_label,
                            :variant,
                            :source_url,
                            :score,
                            :score_breakdown_json,
                            :candidate_status,
                            :is_probable,
                            :is_user_confirmed,
                            :is_external_database_override,
                            :created_by,
                            :created_at,
                            :updated_at
                        )
                        """
                    ),
                    params,
                )
                saved.append(candidate_id)

    return {
        "ok": True,
        "context_key": context_key,
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "candidate_count": len(candidates),
        "saved_count": len(saved),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "saved_candidate_ids": saved,
        "updated_candidate_ids": updated,
        "skipped": skipped,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_saved_external_product_candidates(context_key: str | None = None, limit: int = 50) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_limit = max(1, min(int(limit or 50), 200))
    with engine.begin() as conn:
        if context_key:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM external_product_candidates
                    WHERE context_key = :context_key
                    ORDER BY score DESC, updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"context_key": context_key, "limit": normalized_limit},
            ).mappings().all()
        else:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM external_product_candidates
                    ORDER BY updated_at DESC, score DESC
                    LIMIT :limit
                    """
                ),
                {"limit": normalized_limit},
            ).mappings().all()
    return {"items": [dict(row) for row in rows]}
