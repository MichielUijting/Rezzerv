from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import ensure_external_product_candidates_schema

DEFAULT_PROMOTION_THRESHOLD = 0.85

GLOBAL_PRODUCT_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "canonical_name": "TEXT",
    "brand": "TEXT",
    "product_type": "TEXT",
    "category": "TEXT",
    "retailer_article_number": "TEXT",
    "gtin": "TEXT",
    "source_name": "TEXT",
    "source_product_code": "TEXT",
    "source_url": "TEXT",
    "promotion_status": "TEXT",
    "created_by": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

PRODUCT_ENRICHMENT_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "global_product_id": "TEXT",
    "external_product_candidate_id": "TEXT",
    "context_key": "TEXT",
    "source_name": "TEXT",
    "source_product_code": "TEXT",
    "retailer_code": "TEXT",
    "retailer_article_number": "TEXT",
    "candidate_name": "TEXT",
    "candidate_brand": "TEXT",
    "variant": "TEXT",
    "quantity_label": "TEXT",
    "source_url": "TEXT",
    "score": "REAL",
    "promotion_threshold": "REAL",
    "promotion_status": "TEXT",
    "relationship_status": "TEXT",
    "created_by": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

CREATE_GLOBAL_PRODUCTS_SQL = """
CREATE TABLE IF NOT EXISTS global_products (
    id TEXT PRIMARY KEY,
    canonical_name TEXT,
    brand TEXT,
    product_type TEXT,
    category TEXT,
    retailer_article_number TEXT,
    gtin TEXT,
    source_name TEXT,
    source_product_code TEXT,
    source_url TEXT,
    promotion_status TEXT,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

CREATE_PRODUCT_ENRICHMENTS_SQL = """
CREATE TABLE IF NOT EXISTS product_enrichments (
    id TEXT PRIMARY KEY,
    global_product_id TEXT,
    external_product_candidate_id TEXT,
    context_key TEXT,
    source_name TEXT,
    source_product_code TEXT,
    retailer_code TEXT,
    retailer_article_number TEXT,
    candidate_name TEXT,
    candidate_brand TEXT,
    variant TEXT,
    quantity_label TEXT,
    source_url TEXT,
    score REAL,
    promotion_threshold REAL,
    promotion_status TEXT,
    relationship_status TEXT,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

GLOBAL_PRODUCTS_SOURCE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_global_products_source
ON global_products (source_name, source_product_code, retailer_article_number)
"""

PRODUCT_ENRICHMENTS_SOURCE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_enrichments_source
ON product_enrichments (source_name, source_product_code, context_key, variant)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_sqlite_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {str(row.get("name") or "") for row in rows}


def _get_postgres_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _add_missing_columns(conn, table_name: str, columns: dict[str, str]) -> None:
    dialect_name = str(engine.dialect.name or "").lower()
    existing_columns = _get_sqlite_columns(conn, table_name) if dialect_name == "sqlite" else _get_postgres_columns(conn, table_name)
    for column_name, column_definition in columns.items():
        if column_name in existing_columns or column_name == "id":
            continue
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))


def ensure_catalog_schema() -> None:
    ensure_external_product_candidates_schema()
    with engine.begin() as conn:
        conn.execute(text(CREATE_GLOBAL_PRODUCTS_SQL))
        conn.execute(text(CREATE_PRODUCT_ENRICHMENTS_SQL))
        _add_missing_columns(conn, "global_products", GLOBAL_PRODUCT_COLUMNS)
        _add_missing_columns(conn, "product_enrichments", PRODUCT_ENRICHMENT_COLUMNS)
        conn.execute(text(GLOBAL_PRODUCTS_SOURCE_INDEX_SQL))
        conn.execute(text(PRODUCT_ENRICHMENTS_SOURCE_INDEX_SQL))


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


def _find_existing_enrichment(conn, candidate: dict[str, Any]):
    source_name = _candidate_source_name(candidate)
    source_product_code = _candidate_source_product_code(candidate)
    return conn.execute(
        text(
            """
            SELECT *
            FROM product_enrichments
            WHERE COALESCE(source_name, '') = COALESCE(:source_name, '')
              AND COALESCE(source_product_code, '') = COALESCE(:source_product_code, '')
              AND COALESCE(context_key, '') = COALESCE(:context_key, '')
              AND COALESCE(variant, '') = COALESCE(:variant, '')
            LIMIT 1
            """
        ),
        {
            "source_name": source_name,
            "source_product_code": source_product_code,
            "context_key": str(candidate.get("context_key") or "").strip(),
            "variant": str(candidate.get("variant") or "").strip(),
        },
    ).mappings().first()


def _find_existing_global_product(conn, source_name: str, source_product_code: str, retailer_article_number: str | None):
    return conn.execute(
        text(
            """
            SELECT *
            FROM global_products
            WHERE COALESCE(source_name, '') = COALESCE(:source_name, '')
              AND COALESCE(source_product_code, '') = COALESCE(:source_product_code, '')
              AND COALESCE(retailer_article_number, '') = COALESCE(:retailer_article_number, '')
            LIMIT 1
            """
        ),
        {
            "source_name": source_name,
            "source_product_code": source_product_code,
            "retailer_article_number": str(retailer_article_number or "").strip(),
        },
    ).mappings().first()


def promote_highest_candidate_to_catalog(
    context_key: str | None = None,
    retailer_code: str | None = None,
    receipt_line_text: str | None = None,
    threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> dict[str, Any]:
    ensure_catalog_schema()
    normalized_threshold = float(threshold or DEFAULT_PROMOTION_THRESHOLD)
    timestamp = now_iso()

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
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        candidate = dict(candidate_row)
        source_name = _candidate_source_name(candidate)
        source_product_code = _candidate_source_product_code(candidate)
        retailer_article_number = str(candidate.get("retailer_article_number") or "").strip() or None
        existing_enrichment = _find_existing_enrichment(conn, candidate)
        existing_product = _find_existing_global_product(conn, source_name, source_product_code, retailer_article_number)
        global_product_id = str(existing_product.get("id")) if existing_product else str(uuid.uuid4())
        enrichment_id = str(existing_enrichment.get("id")) if existing_enrichment else str(uuid.uuid4())

        product_params = {
            "id": global_product_id,
            "canonical_name": str(candidate.get("candidate_name") or "").strip(),
            "brand": str(candidate.get("candidate_brand") or "").strip() or None,
            "product_type": None,
            "category": None,
            "retailer_article_number": retailer_article_number,
            "gtin": None,
            "source_name": source_name,
            "source_product_code": source_product_code,
            "source_url": str(candidate.get("source_url") or "").strip() or None,
            "promotion_status": "catalog_promoted_from_external_candidate",
            "created_by": "external_database_catalog_promotion_v1",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        enrichment_params = {
            "id": enrichment_id,
            "global_product_id": global_product_id,
            "external_product_candidate_id": str(candidate.get("id") or "").strip(),
            "context_key": str(candidate.get("context_key") or "").strip(),
            "source_name": source_name,
            "source_product_code": source_product_code,
            "retailer_code": str(candidate.get("retailer_code") or "").strip() or None,
            "retailer_article_number": retailer_article_number,
            "candidate_name": str(candidate.get("candidate_name") or "").strip(),
            "candidate_brand": str(candidate.get("candidate_brand") or "").strip() or None,
            "variant": str(candidate.get("variant") or "").strip() or None,
            "quantity_label": str(candidate.get("quantity_label") or "").strip() or None,
            "source_url": str(candidate.get("source_url") or "").strip() or None,
            "score": float(candidate.get("score") or 0),
            "promotion_threshold": normalized_threshold,
            "promotion_status": "catalog_promoted",
            "relationship_status": "proposed_by_external_database",
            "created_by": "external_database_catalog_promotion_v1",
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        if existing_product:
            conn.execute(
                text(
                    """
                    UPDATE global_products
                    SET canonical_name = :canonical_name,
                        brand = :brand,
                        retailer_article_number = :retailer_article_number,
                        source_url = :source_url,
                        promotion_status = :promotion_status,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                product_params,
            )
            product_action = "updated"
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO global_products (
                        id, canonical_name, brand, product_type, category, retailer_article_number, gtin,
                        source_name, source_product_code, source_url, promotion_status, created_by, created_at, updated_at
                    ) VALUES (
                        :id, :canonical_name, :brand, :product_type, :category, :retailer_article_number, :gtin,
                        :source_name, :source_product_code, :source_url, :promotion_status, :created_by, :created_at, :updated_at
                    )
                    """
                ),
                product_params,
            )
            product_action = "created"

        if existing_enrichment:
            conn.execute(
                text(
                    """
                    UPDATE product_enrichments
                    SET global_product_id = :global_product_id,
                        external_product_candidate_id = :external_product_candidate_id,
                        candidate_name = :candidate_name,
                        candidate_brand = :candidate_brand,
                        quantity_label = :quantity_label,
                        source_url = :source_url,
                        score = :score,
                        promotion_threshold = :promotion_threshold,
                        promotion_status = :promotion_status,
                        relationship_status = :relationship_status,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                enrichment_params,
            )
            enrichment_action = "updated"
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO product_enrichments (
                        id, global_product_id, external_product_candidate_id, context_key, source_name, source_product_code,
                        retailer_code, retailer_article_number, candidate_name, candidate_brand, variant, quantity_label,
                        source_url, score, promotion_threshold, promotion_status, relationship_status,
                        created_by, created_at, updated_at
                    ) VALUES (
                        :id, :global_product_id, :external_product_candidate_id, :context_key, :source_name, :source_product_code,
                        :retailer_code, :retailer_article_number, :candidate_name, :candidate_brand, :variant, :quantity_label,
                        :source_url, :score, :promotion_threshold, :promotion_status, :relationship_status,
                        :created_by, :created_at, :updated_at
                    )
                    """
                ),
                enrichment_params,
            )
            enrichment_action = "created"

    return {
        "ok": True,
        "promoted": True,
        "global_product_id": global_product_id,
        "product_enrichment_id": enrichment_id,
        "product_action": product_action,
        "enrichment_action": enrichment_action,
        "candidate_id": str(candidate.get("id") or ""),
        "candidate_name": str(candidate.get("candidate_name") or ""),
        "candidate_brand": str(candidate.get("candidate_brand") or ""),
        "score": float(candidate.get("score") or 0),
        "promotion_threshold": normalized_threshold,
        "source_name": source_name,
        "source_product_code": source_product_code,
        "retailer_article_number": retailer_article_number,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_catalog_products(limit: int = 50) -> dict[str, Any]:
    ensure_catalog_schema()
    normalized_limit = max(1, min(int(limit or 50), 200))
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM global_products
                ORDER BY updated_at DESC, canonical_name ASC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()
    return {"items": [dict(row) for row in rows]}
