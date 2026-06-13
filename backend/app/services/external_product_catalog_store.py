from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import ensure_external_product_candidates_schema

DEFAULT_PROMOTION_THRESHOLD = 0.85


def _candidate_source_name(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_source_name") or candidate.get("source_name") or "external_database").strip()


def _candidate_source_product_code(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("candidate_source_product_code")
        or candidate.get("source_product_code")
        or candidate.get("retailer_article_number")
        or "unknown"
    ).strip()


def _find_highest_candidate(conn, context_key: str | None, retailer_code: str | None, receipt_line_text: str | None, threshold: float):
    params: dict[str, Any] = {"threshold": threshold}
    where_parts = ["COALESCE(score, 0) >= :threshold"]
    if context_key:
        where_parts.append("context_key = :context_key")
        params["context_key"] = context_key
    if retailer_code:
        where_parts.append("retailer_code = :retailer_code")
        params["retailer_code"] = retailer_code.strip().lower()
    if receipt_line_text:
        where_parts.append("receipt_line_text = :receipt_line_text")
        params["receipt_line_text"] = receipt_line_text
    where_sql = " AND ".join(where_parts)
    return conn.execute(
        text(
            f"""
            SELECT *
            FROM external_product_candidates
            WHERE {where_sql}
            ORDER BY score DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()


def _find_existing_global_product(conn, candidate: dict[str, Any]):
    candidate_name = str(candidate.get("candidate_name") or "").strip()
    candidate_brand = str(candidate.get("candidate_brand") or "").strip()
    candidate_variant = str(candidate.get("variant") or "").strip()
    source_product_code = _candidate_source_product_code(candidate)

    if source_product_code and source_product_code != "unknown":
        identity_match = conn.execute(
            text(
                """
                SELECT gp.*
                FROM product_identities pi
                JOIN global_products gp ON gp.id = pi.global_product_id
                WHERE pi.identity_value = :identity_value
                LIMIT 1
                """
            ),
            {"identity_value": source_product_code},
        ).mappings().first()
        if identity_match:
            return identity_match

    if candidate_name:
        return conn.execute(
            text(
                """
                SELECT *
                FROM global_products
                WHERE lower(name) = lower(:name)
                  AND COALESCE(lower(brand), '') = COALESCE(lower(:brand), '')
                  AND COALESCE(lower(variant), '') = COALESCE(lower(:variant), '')
                LIMIT 1
                """
            ),
            {
                "name": candidate_name,
                "brand": candidate_brand,
                "variant": candidate_variant,
            },
        ).mappings().first()

    return None


def promote_highest_candidate_to_catalog(
    context_key: str | None = None,
    retailer_code: str | None = None,
    receipt_line_text: str | None = None,
    threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> dict[str, Any]:
    """Link the highest external candidate to an existing global product only.

    M2C2e deliberately does not create global_products and does not write
    product_enrichments from standalone preview context, because the current
    runtime product_enrichments table requires a household_article_id.
    """
    ensure_external_product_candidates_schema()
    normalized_threshold = float(threshold or DEFAULT_PROMOTION_THRESHOLD)

    with engine.begin() as conn:
        candidate_row = _find_highest_candidate(
            conn,
            context_key=context_key,
            retailer_code=retailer_code,
            receipt_line_text=receipt_line_text,
            threshold=normalized_threshold,
        )
        if not candidate_row:
            return {
                "ok": True,
                "promoted": False,
                "reason": "no_candidate_above_threshold",
                "promotion_threshold": normalized_threshold,
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        candidate = dict(candidate_row)
        existing_global_product = _find_existing_global_product(conn, candidate)
        if not existing_global_product:
            return {
                "ok": True,
                "promoted": False,
                "reason": "blocked_requires_existing_global_product",
                "candidate_id": str(candidate.get("id") or ""),
                "candidate_name": str(candidate.get("candidate_name") or ""),
                "candidate_brand": str(candidate.get("candidate_brand") or ""),
                "source_name": _candidate_source_name(candidate),
                "source_product_code": _candidate_source_product_code(candidate),
                "score": float(candidate.get("score") or 0),
                "promotion_threshold": normalized_threshold,
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        global_product_id = str(existing_global_product.get("id") or "")
        candidate_id = str(candidate.get("id") or "")
        conn.execute(
            text(
                """
                UPDATE external_product_candidates
                SET global_product_id = :global_product_id,
                    status = 'linked_to_catalog',
                    candidate_status = 'linked_to_catalog',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {"global_product_id": global_product_id, "candidate_id": candidate_id},
        )

    return {
        "ok": True,
        "promoted": True,
        "reason": "linked_to_existing_global_product",
        "global_product_id": global_product_id,
        "candidate_id": candidate_id,
        "candidate_name": str(candidate.get("candidate_name") or ""),
        "candidate_brand": str(candidate.get("candidate_brand") or ""),
        "score": float(candidate.get("score") or 0),
        "promotion_threshold": normalized_threshold,
        "source_name": _candidate_source_name(candidate),
        "source_product_code": _candidate_source_product_code(candidate),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_catalog_products(limit: int = 50) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 50), 200))
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM global_products
                ORDER BY updated_at DESC, name ASC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()
    return {"items": [dict(row) for row in rows]}
