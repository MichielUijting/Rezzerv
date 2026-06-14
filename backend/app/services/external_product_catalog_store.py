from __future__ import annotations

import uuid
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


def _candidate_title(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_name") or candidate.get("global_product_name") or "").strip()


def _candidate_brand(candidate: dict[str, Any]) -> str | None:
    value = str(candidate.get("candidate_brand") or candidate.get("global_product_brand") or "").strip()
    return value or None


def _candidate_variant(candidate: dict[str, Any]) -> str | None:
    value = str(candidate.get("variant") or candidate.get("global_product_variant") or "").strip()
    return value or None


def _candidate_category(candidate: dict[str, Any]) -> str | None:
    value = str(candidate.get("candidate_category") or candidate.get("global_product_category") or "").strip()
    return value or None


def _table_id_is_integer(conn, table_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    for row in rows:
        if str(row.get("name") or "") == "id":
            return "INT" in str(row.get("type") or "").upper()
    return False


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


def _find_candidate_by_id(conn, candidate_id: str):
    return conn.execute(
        text(
            """
            SELECT *
            FROM external_product_candidates
            WHERE id = :candidate_id
            LIMIT 1
            """
        ),
        {"candidate_id": candidate_id},
    ).mappings().first()


def _find_catalog_link_for_receipt_context(conn, candidate: dict[str, Any]):
    context_key = str(candidate.get("context_key") or "").strip()
    receipt_line_text = str(candidate.get("receipt_line_text") or "").strip()
    params: dict[str, Any] = {}
    where_parts = ["global_product_id IS NOT NULL"]
    if context_key:
        where_parts.append("context_key = :context_key")
        params["context_key"] = context_key
    elif receipt_line_text:
        where_parts.append("receipt_line_text = :receipt_line_text")
        params["receipt_line_text"] = receipt_line_text
    else:
        return None
    return conn.execute(
        text(
            f"""
            SELECT id, candidate_name, global_product_id, receipt_line_text
            FROM external_product_candidates
            WHERE {' AND '.join(where_parts)}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()


def _find_existing_global_product(conn, candidate: dict[str, Any]):
    explicit_global_product_id = str(candidate.get("global_product_id") or "").strip()
    if explicit_global_product_id:
        direct_match = conn.execute(
            text(
                """
                SELECT *
                FROM global_products
                WHERE id = :global_product_id
                LIMIT 1
                """
            ),
            {"global_product_id": explicit_global_product_id},
        ).mappings().first()
        if direct_match:
            return direct_match

    source_product_code = _candidate_source_product_code(candidate)
    if source_product_code and source_product_code != "unknown":
        identity_match = conn.execute(
            text(
                """
                SELECT gp.*
                FROM product_identities pi
                JOIN global_products gp ON gp.id = pi.global_product_id
                WHERE pi.identity_value = :identity_value
                  AND pi.global_product_id IS NOT NULL
                LIMIT 1
                """
            ),
            {"identity_value": source_product_code},
        ).mappings().first()
        if identity_match:
            return identity_match

    candidate_name = _candidate_title(candidate)
    candidate_brand = _candidate_brand(candidate) or ""
    candidate_variant = _candidate_variant(candidate) or ""
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


def _create_global_product_from_candidate(conn, candidate: dict[str, Any]) -> str:
    product_name = _candidate_title(candidate)
    if not product_name:
        raise ValueError("candidate_name_required")

    params = {
        "id": str(uuid.uuid4()),
        "name": product_name,
        "brand": _candidate_brand(candidate),
        "variant": _candidate_variant(candidate),
        "category": _candidate_category(candidate),
        "source": _candidate_source_name(candidate) or "external_database",
        "status": "active",
    }
    if _table_id_is_integer(conn, "global_products"):
        result = conn.execute(
            text(
                """
                INSERT INTO global_products (name, brand, variant, category, source, status)
                VALUES (:name, :brand, :variant, :category, :source, :status)
                """
            ),
            params,
        )
        return str(result.lastrowid)

    conn.execute(
        text(
            """
            INSERT INTO global_products (id, name, brand, variant, category, source, status)
            VALUES (:id, :name, :brand, :variant, :category, :source, :status)
            """
        ),
        params,
    )
    return str(params["id"])


def _upsert_product_identity(conn, global_product_id: str, candidate: dict[str, Any]) -> None:
    identity_value = _candidate_source_product_code(candidate)
    if not identity_value or identity_value == "unknown":
        return
    params = {
        "id": str(uuid.uuid4()),
        "global_product_id": global_product_id,
        "identity_type": "external_article_number",
        "identity_value": identity_value,
        "source": _candidate_source_name(candidate),
        "confidence_score": float(candidate.get("score") or 0),
        "is_primary": 0,
    }
    if _table_id_is_integer(conn, "product_identities"):
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO product_identities (
                    global_product_id, identity_type, identity_value, source, confidence_score, is_primary
                ) VALUES (
                    :global_product_id, :identity_type, :identity_value, :source, :confidence_score, :is_primary
                )
                """
            ),
            params,
        )
        return
    conn.execute(
        text(
            """
            INSERT OR IGNORE INTO product_identities (
                id, global_product_id, identity_type, identity_value, source, confidence_score, is_primary
            ) VALUES (
                :id, :global_product_id, :identity_type, :identity_value, :source, :confidence_score, :is_primary
            )
            """
        ),
        params,
    )


def _mark_candidate_linked(conn, candidate_id: str, global_product_id: str) -> None:
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


def _already_linked_result(candidate: dict[str, Any], linked: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "promoted": False,
        "already_linked": True,
        "reason": "receipt_line_already_has_catalog_candidate",
        "message": "Dit bonartikel heeft al een kandidaatartikel in de catalogus.",
        "candidate_id": str(candidate.get("id") or ""),
        "candidate_name": _candidate_title(candidate),
        "linked_candidate_id": str(linked.get("id") or ""),
        "linked_candidate_name": str(linked.get("candidate_name") or ""),
        "global_product_id": str(linked.get("global_product_id") or ""),
        "receipt_line_text": str(linked.get("receipt_line_text") or candidate.get("receipt_line_text") or ""),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def _promote_candidate_row(conn, candidate: dict[str, Any], allow_create: bool) -> dict[str, Any]:
    candidate_id = str(candidate.get("id") or "")
    linked_for_context = _find_catalog_link_for_receipt_context(conn, candidate)
    if linked_for_context:
        return _already_linked_result(candidate, dict(linked_for_context))

    existing_global_product = _find_existing_global_product(conn, candidate)
    created_global_product = False

    if existing_global_product:
        global_product_id = str(existing_global_product.get("id") or "")
        reason = "linked_to_existing_global_product"
    elif allow_create:
        global_product_id = _create_global_product_from_candidate(conn, candidate)
        _upsert_product_identity(conn, global_product_id, candidate)
        created_global_product = True
        reason = "created_global_product_from_confirmed_candidate"
    else:
        return {
            "ok": True,
            "promoted": False,
            "reason": "blocked_requires_existing_global_product",
            "candidate_id": candidate_id,
            "candidate_name": _candidate_title(candidate),
            "candidate_brand": _candidate_brand(candidate) or "",
            "source_name": _candidate_source_name(candidate),
            "source_product_code": _candidate_source_product_code(candidate),
            "score": float(candidate.get("score") or 0),
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    _mark_candidate_linked(conn, candidate_id, global_product_id)
    return {
        "ok": True,
        "promoted": True,
        "already_linked": False,
        "reason": reason,
        "global_product_id": global_product_id,
        "candidate_id": candidate_id,
        "candidate_name": _candidate_title(candidate),
        "candidate_brand": _candidate_brand(candidate) or "",
        "score": float(candidate.get("score") or 0),
        "source_name": _candidate_source_name(candidate),
        "source_product_code": _candidate_source_product_code(candidate),
        "creates_global_product": created_global_product,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def promote_highest_candidate_to_catalog(
    context_key: str | None = None,
    retailer_code: str | None = None,
    receipt_line_text: str | None = None,
    threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> dict[str, Any]:
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

        result = _promote_candidate_row(conn, dict(candidate_row), allow_create=False)
        result["promotion_threshold"] = normalized_threshold
        return result


def process_selected_candidates_to_catalog(candidate_ids: list[str], allow_create: bool = True) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_ids = [str(candidate_id or "").strip() for candidate_id in candidate_ids]
    normalized_ids = [candidate_id for candidate_id in normalized_ids if candidate_id]
    if not normalized_ids:
        return {"ok": False, "reason": "candidate_ids_required", "results": []}

    results: list[dict[str, Any]] = []
    with engine.begin() as conn:
        for candidate_id in normalized_ids:
            candidate_row = _find_candidate_by_id(conn, candidate_id)
            if not candidate_row:
                results.append({"ok": False, "candidate_id": candidate_id, "reason": "candidate_not_found"})
                continue
            results.append(_promote_candidate_row(conn, dict(candidate_row), allow_create=allow_create))

    return {
        "ok": True,
        "processed_count": len(results),
        "promoted_count": sum(1 for item in results if item.get("promoted")),
        "already_linked_count": sum(1 for item in results if item.get("already_linked")),
        "created_global_products_count": sum(1 for item in results if item.get("creates_global_product")),
        "creates_household_article": False,
        "creates_inventory_event": False,
        "results": results,
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
