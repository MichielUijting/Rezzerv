from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from app.db import engine


BATCH_DECISIONS_SQL = """
CREATE TABLE IF NOT EXISTS external_relation_batch_decisions (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    household_article_id TEXT,
    global_product_id TEXT,
    decision TEXT NOT NULL,
    decision_reason TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
)
"""

BATCH_DECISIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_external_relation_batch_decisions_candidate
ON external_relation_batch_decisions (candidate_id, household_article_id, decision)
"""


def ensure_external_relation_batch_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(BATCH_DECISIONS_SQL))
        conn.execute(text(BATCH_DECISIONS_INDEX_SQL))


def _candidate_source_name(row: dict[str, Any]) -> str:
    return str(row.get("candidate_source_name") or row.get("source_name") or "external_database").strip()


def _candidate_source_record_id(row: dict[str, Any]) -> str:
    return str(
        row.get("candidate_source_product_code")
        or row.get("source_product_code")
        or row.get("retailer_article_number")
        or row.get("id")
        or "unknown"
    ).strip()


def _relation_status(row: dict[str, Any]) -> tuple[bool, str, str]:
    if not str(row.get("global_product_id") or "").strip():
        return False, "no_catalog_link", "Nog geen cataloguskoppeling"
    if not str(row.get("household_article_id") or "").strip():
        return False, "no_household_match", "Nog geen huishoudartikelmatch"
    return True, "linkable", "Koppelbaar"


def list_external_relation_batch_items(household_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    ensure_external_relation_batch_schema()
    normalized_limit = max(1, min(int(limit or 50), 200))
    params: dict[str, Any] = {"limit": normalized_limit}
    household_join_filter = ""
    if household_id:
        household_join_filter = "AND ha.household_id = :household_id"
        params["household_id"] = household_id

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    epc.id AS candidate_id,
                    epc.global_product_id AS global_product_id,
                    epc.candidate_name AS candidate_name,
                    epc.candidate_brand AS candidate_brand,
                    epc.candidate_category AS candidate_category,
                    epc.source_name AS source_name,
                    epc.source_product_code AS source_product_code,
                    epc.candidate_source_name AS candidate_source_name,
                    epc.candidate_source_product_code AS candidate_source_product_code,
                    epc.retailer_article_number AS retailer_article_number,
                    epc.source_url AS source_url,
                    epc.candidate_source_url AS candidate_source_url,
                    epc.score AS score,
                    epc.status AS candidate_storage_status,
                    epc.candidate_status AS candidate_match_status,
                    epc.raw_payload AS raw_payload,
                    ha.id AS household_article_id,
                    ha.household_id AS household_id,
                    ha.naam AS household_article_name,
                    ha.global_product_id AS household_global_product_id,
                    ha.external_source AS household_external_source,
                    gp.name AS global_product_name,
                    gp.brand AS global_product_brand,
                    gp.variant AS global_product_variant,
                    gp.category AS global_product_category,
                    d.decision AS last_decision
                FROM external_product_candidates epc
                LEFT JOIN global_products gp ON gp.id = epc.global_product_id
                LEFT JOIN household_articles ha
                  ON ha.global_product_id = epc.global_product_id
                 AND COALESCE(ha.status, 'active') = 'active'
                 {household_join_filter}
                LEFT JOIN external_relation_batch_decisions d
                  ON d.candidate_id = epc.id
                 AND COALESCE(d.household_article_id, '') = COALESCE(ha.id, '')
                 AND d.decision IN ('apply', 'skip')
                WHERE d.id IS NULL
                ORDER BY epc.score DESC, epc.updated_at DESC, epc.created_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        can_link, status_code, status_label = _relation_status(item)
        item["can_link"] = can_link
        item["relation_status"] = status_code
        item["relation_status_label"] = status_label
        items.append(item)
    return {"items": items}


def _find_candidate_household_pair(conn, candidate_id: str, household_article_id: str):
    return conn.execute(
        text(
            """
            SELECT
                epc.*,
                ha.id AS household_article_id,
                ha.household_id AS household_id,
                ha.naam AS household_article_name,
                gp.name AS global_product_name,
                gp.brand AS global_product_brand,
                gp.category AS global_product_category
            FROM external_product_candidates epc
            JOIN household_articles ha ON ha.global_product_id = epc.global_product_id
            JOIN global_products gp ON gp.id = epc.global_product_id
            WHERE epc.id = :candidate_id
              AND ha.id = :household_article_id
              AND epc.global_product_id IS NOT NULL
            LIMIT 1
            """
        ),
        {"candidate_id": candidate_id, "household_article_id": household_article_id},
    ).mappings().first()


def _find_existing_enrichment(conn, household_article_id: str, source_name: str, source_record_id: str):
    return conn.execute(
        text(
            """
            SELECT *
            FROM product_enrichments
            WHERE household_article_id = :household_article_id
              AND source_name = :source_name
              AND COALESCE(source_record_id, '') = COALESCE(:source_record_id, '')
            LIMIT 1
            """
        ),
        {
            "household_article_id": household_article_id,
            "source_name": source_name,
            "source_record_id": source_record_id,
        },
    ).mappings().first()


def _upsert_decision(
    conn,
    candidate_id: str,
    household_article_id: str | None,
    global_product_id: str | None,
    decision: str,
    decision_reason: str | None,
    created_by: str,
) -> None:
    existing = conn.execute(
        text(
            """
            SELECT id
            FROM external_relation_batch_decisions
            WHERE candidate_id = :candidate_id
              AND COALESCE(household_article_id, '') = COALESCE(:household_article_id, '')
              AND decision = :decision
            LIMIT 1
            """
        ),
        {
            "candidate_id": candidate_id,
            "household_article_id": household_article_id,
            "decision": decision,
        },
    ).mappings().first()
    params = {
        "id": str(existing.get("id")) if existing else str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "household_article_id": household_article_id,
        "global_product_id": global_product_id,
        "decision": decision,
        "decision_reason": decision_reason,
        "created_by": created_by,
    }
    if existing:
        conn.execute(
            text(
                """
                UPDATE external_relation_batch_decisions
                SET global_product_id = :global_product_id,
                    decision_reason = :decision_reason,
                    created_by = :created_by,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            params,
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO external_relation_batch_decisions (
                    id, candidate_id, household_article_id, global_product_id,
                    decision, decision_reason, created_by
                ) VALUES (
                    :id, :candidate_id, :household_article_id, :global_product_id,
                    :decision, :decision_reason, :created_by
                )
                """
            ),
            params,
        )


def apply_external_relation_batch_decision(
    candidate_id: str,
    household_article_id: str | None = None,
    decision: str = "later",
    decision_reason: str | None = None,
    created_by: str = "admin_external_relation_batch_v1",
) -> dict[str, Any]:
    ensure_external_relation_batch_schema()
    normalized_decision = str(decision or "later").strip().lower()
    if normalized_decision not in {"apply", "skip", "later"}:
        return {"ok": False, "reason": "invalid_decision", "allowed": ["apply", "skip", "later"]}

    if not candidate_id:
        return {"ok": False, "reason": "candidate_id_required"}

    with engine.begin() as conn:
        if normalized_decision == "later":
            _upsert_decision(conn, candidate_id, household_article_id, None, "later", decision_reason, created_by)
            return {
                "ok": True,
                "decision": "later",
                "applied": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        if not household_article_id:
            return {"ok": False, "reason": "household_article_id_required"}

        pair = _find_candidate_household_pair(conn, candidate_id, household_article_id)
        if not pair:
            return {
                "ok": False,
                "reason": "candidate_household_article_pair_not_found",
                "applied": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        row = dict(pair)
        global_product_id = str(row.get("global_product_id") or "").strip()
        if normalized_decision == "skip":
            _upsert_decision(conn, candidate_id, household_article_id, global_product_id, "skip", decision_reason, created_by)
            return {
                "ok": True,
                "decision": "skip",
                "applied": False,
                "candidate_id": candidate_id,
                "household_article_id": household_article_id,
                "global_product_id": global_product_id,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        source_name = _candidate_source_name(row)
        source_record_id = _candidate_source_record_id(row)
        existing = _find_existing_enrichment(conn, household_article_id, source_name, source_record_id)
        enrichment_id = str(existing.get("id")) if existing else str(uuid.uuid4())
        raw_payload_json = row.get("raw_payload")
        if raw_payload_json and not isinstance(raw_payload_json, str):
            raw_payload_json = json.dumps(raw_payload_json, ensure_ascii=False)
        params = {
            "id": enrichment_id,
            "household_article_id": household_article_id,
            "source_name": source_name,
            "source_record_id": source_record_id,
            "title": str(row.get("candidate_name") or row.get("global_product_name") or row.get("household_article_name") or "").strip() or None,
            "brand": str(row.get("candidate_brand") or row.get("global_product_brand") or "").strip() or None,
            "category": str(row.get("candidate_category") or row.get("global_product_category") or "").strip() or None,
            "source_url": str(row.get("source_url") or row.get("candidate_source_url") or "").strip() or None,
            "quality_score": float(row.get("score") or 0),
            "raw_payload_json": raw_payload_json,
            "lookup_status": "applied_from_external_relation_batch",
            "last_lookup_source": source_name,
            "last_lookup_message": "M2C2f admin batch apply",
            "global_product_id": global_product_id,
        }
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE product_enrichments
                    SET title = :title,
                        brand = :brand,
                        category = :category,
                        source_url = :source_url,
                        quality_score = :quality_score,
                        raw_payload_json = :raw_payload_json,
                        lookup_status = :lookup_status,
                        last_lookup_at = CURRENT_TIMESTAMP,
                        last_lookup_source = :last_lookup_source,
                        last_lookup_message = :last_lookup_message,
                        global_product_id = :global_product_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                params,
            )
            enrichment_action = "updated"
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO product_enrichments (
                        id, household_article_id, source_name, source_record_id,
                        title, brand, category, source_url, quality_score,
                        raw_payload_json, lookup_status, last_lookup_at,
                        last_lookup_source, last_lookup_message, global_product_id
                    ) VALUES (
                        :id, :household_article_id, :source_name, :source_record_id,
                        :title, :brand, :category, :source_url, :quality_score,
                        :raw_payload_json, :lookup_status, CURRENT_TIMESTAMP,
                        :last_lookup_source, :last_lookup_message, :global_product_id
                    )
                    """
                ),
                params,
            )
            enrichment_action = "created"

        conn.execute(
            text(
                """
                UPDATE external_product_candidates
                SET status = 'external_relation_applied',
                    candidate_status = 'external_relation_applied',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {"candidate_id": candidate_id},
        )
        _upsert_decision(conn, candidate_id, household_article_id, global_product_id, "apply", decision_reason, created_by)

    return {
        "ok": True,
        "decision": "apply",
        "applied": True,
        "candidate_id": candidate_id,
        "household_article_id": household_article_id,
        "global_product_id": global_product_id,
        "enrichment_id": enrichment_id,
        "enrichment_action": enrichment_action,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
