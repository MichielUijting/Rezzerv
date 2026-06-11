from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app import main as main_app
from app.db import engine

app = main_app.app


EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS = "open_food_facts"
EXTERNAL_PRODUCT_ALLOWED_SOURCES = {EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS, "public_reference_catalog", "gs1_my_product_manager_share"}


def normalize_external_source_name(value: str | None) -> str:
    normalized = str(value or EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS).strip().lower().replace("-", "_")
    if normalized in {"off", "openfoodfacts", "open_food_fact"}:
        return EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS
    return normalized if normalized in EXTERNAL_PRODUCT_ALLOWED_SOURCES else EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS


def normalize_external_gtin(value: str | None) -> str | None:
    normalized = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return normalized[:32] if normalized else None


def normalize_external_text(value: Any, max_length: int | None = None) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    return normalized[:max_length] if max_length else normalized


def build_external_search_text(*values: Any) -> str:
    parts = [normalize_external_text(value) for value in values]
    cleaned = " ".join(part for part in parts if part)
    cleaned = re.sub(r"[^\w\s]+", " ", cleaned, flags=re.UNICODE)
    return " ".join(cleaned.lower().split())


def ensure_external_product_index_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS external_product_index (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_product_code TEXT,
                gtin TEXT,
                product_name TEXT NOT NULL,
                brand TEXT,
                category TEXT,
                quantity_label TEXT,
                image_url TEXT,
                source_url TEXT,
                search_text TEXT NOT NULL,
                raw_payload_json TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_name, source_product_code)
            )
            """
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_external_product_index_gtin ON external_product_index (gtin) WHERE gtin IS NOT NULL AND trim(gtin) <> ''"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_external_product_index_source_gtin ON external_product_index (source_name, gtin) WHERE gtin IS NOT NULL AND trim(gtin) <> ''"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_external_product_index_search_text ON external_product_index (search_text)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_external_product_index_updated_at ON external_product_index (updated_at DESC)"
        ))


class ExternalProductIndexUpsertRequest(BaseModel):
    source_name: str = EXTERNAL_PRODUCT_SOURCE_OPEN_FOOD_FACTS
    source_product_code: Optional[str] = None
    gtin: Optional[str] = None
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    quantity_label: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    raw_payload_json: Optional[dict[str, Any]] = None

    @field_validator("source_name", mode="before")
    @classmethod
    def validate_source_name(cls, value):
        return normalize_external_source_name(value)

    @field_validator("source_product_code", "gtin", mode="before")
    @classmethod
    def normalize_code_fields(cls, value):
        return normalize_external_gtin(value)

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, value):
        normalized = normalize_external_text(value, 255)
        if not normalized:
            raise ValueError("product_name is verplicht")
        return normalized

    @field_validator("brand", "category", "quantity_label", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        return normalize_external_text(value, 255)


class ExternalProductIndexBulkUpsertRequest(BaseModel):
    products: list[ExternalProductIndexUpsertRequest] = Field(default_factory=list)


class ExternalProductCandidateQuery(BaseModel):
    query: Optional[str] = None
    gtin: Optional[str] = None
    limit: int = 10


def serialize_external_product_row(row: Any, score: float | None = None) -> dict[str, Any]:
    raw_payload = None
    if row.get("raw_payload_json"):
        try:
            raw_payload = json.loads(row.get("raw_payload_json"))
        except Exception:
            raw_payload = None
    payload = {
        "id": row.get("id"),
        "source_name": row.get("source_name"),
        "source_product_code": row.get("source_product_code"),
        "gtin": row.get("gtin"),
        "product_name": row.get("product_name"),
        "brand": row.get("brand"),
        "category": row.get("category"),
        "quantity_label": row.get("quantity_label"),
        "image_url": row.get("image_url"),
        "source_url": row.get("source_url"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "updated_at": row.get("updated_at"),
        "raw_payload_json": raw_payload,
    }
    if score is not None:
        payload["match_score"] = score
    return payload


def upsert_external_product_index_row(conn, item: ExternalProductIndexUpsertRequest) -> dict[str, Any]:
    source_name = normalize_external_source_name(item.source_name)
    gtin = normalize_external_gtin(item.gtin)
    source_product_code = normalize_external_gtin(item.source_product_code) or gtin
    if not source_product_code and not gtin:
        raise HTTPException(status_code=400, detail="source_product_code of gtin is verplicht voor externe productindex")
    search_text = build_external_search_text(item.product_name, item.brand, item.category, item.quantity_label, gtin, source_product_code)
    raw_payload_json = json.dumps(item.raw_payload_json or {}, ensure_ascii=False) if item.raw_payload_json else None

    existing = conn.execute(text(
        """
        SELECT id
        FROM external_product_index
        WHERE source_name = :source_name
          AND source_product_code = :source_product_code
        LIMIT 1
        """
    ), {"source_name": source_name, "source_product_code": source_product_code}).mappings().first()
    row_id = str(existing.get("id")) if existing else str(uuid.uuid4())
    if existing:
        conn.execute(text(
            """
            UPDATE external_product_index
            SET gtin = :gtin,
                product_name = :product_name,
                brand = :brand,
                category = :category,
                quantity_label = :quantity_label,
                image_url = :image_url,
                source_url = :source_url,
                search_text = :search_text,
                raw_payload_json = :raw_payload_json,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ), {
            "id": row_id,
            "gtin": gtin,
            "product_name": item.product_name,
            "brand": item.brand,
            "category": item.category,
            "quantity_label": item.quantity_label,
            "image_url": item.image_url,
            "source_url": item.source_url,
            "search_text": search_text,
            "raw_payload_json": raw_payload_json,
        })
    else:
        conn.execute(text(
            """
            INSERT INTO external_product_index (
                id, source_name, source_product_code, gtin, product_name, brand, category, quantity_label,
                image_url, source_url, search_text, raw_payload_json, first_seen_at, last_seen_at, updated_at
            ) VALUES (
                :id, :source_name, :source_product_code, :gtin, :product_name, :brand, :category, :quantity_label,
                :image_url, :source_url, :search_text, :raw_payload_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ), {
            "id": row_id,
            "source_name": source_name,
            "source_product_code": source_product_code,
            "gtin": gtin,
            "product_name": item.product_name,
            "brand": item.brand,
            "category": item.category,
            "quantity_label": item.quantity_label,
            "image_url": item.image_url,
            "source_url": item.source_url,
            "search_text": search_text,
            "raw_payload_json": raw_payload_json,
        })
    row = conn.execute(text("SELECT * FROM external_product_index WHERE id = :id LIMIT 1"), {"id": row_id}).mappings().first()
    return serialize_external_product_row(row)


def calculate_external_candidate_score(row: Any, query: str | None, gtin: str | None) -> float:
    score = 0.0
    normalized_gtin = normalize_external_gtin(gtin)
    if normalized_gtin and str(row.get("gtin") or "") == normalized_gtin:
        score += 100.0
    query_text = build_external_search_text(query)
    if query_text:
        search_text = str(row.get("search_text") or "").lower()
        if query_text == search_text:
            score += 80.0
        elif query_text in search_text:
            score += 45.0
        for token in [part for part in query_text.split() if len(part) >= 3]:
            if token in search_text:
                score += 10.0
    if row.get("brand"):
        score += 2.0
    if row.get("category"):
        score += 1.0
    return score


def find_external_product_candidates(conn, query: str | None = None, gtin: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    normalized_gtin = normalize_external_gtin(gtin)
    query_text = build_external_search_text(query)
    limit = max(1, min(int(limit or 10), 50))
    params: dict[str, Any] = {"limit": limit * 4}
    where_parts = []
    if normalized_gtin:
        where_parts.append("gtin = :gtin")
        params["gtin"] = normalized_gtin
    if query_text:
        token_parts = [part for part in query_text.split() if len(part) >= 3][:6]
        for index, token in enumerate(token_parts):
            key = f"token_{index}"
            where_parts.append(f"search_text LIKE :{key}")
            params[key] = f"%{token}%"
    if not where_parts:
        return []
    rows = conn.execute(text(
        f"""
        SELECT *
        FROM external_product_index
        WHERE {' OR '.join(where_parts)}
        ORDER BY datetime(updated_at) DESC, id DESC
        LIMIT :limit
        """
    ), params).mappings().all()
    scored = [
        (calculate_external_candidate_score(row, query_text, normalized_gtin), row)
        for row in rows
    ]
    scored = [(score, row) for score, row in scored if score > 0]
    scored.sort(key=lambda item: (-item[0], str(item[1].get("product_name") or "")))
    return [serialize_external_product_row(row, score=score) for score, row in scored[:limit]]


@app.on_event("startup")
def startup_external_product_index_schema() -> None:
    ensure_external_product_index_schema()


@app.post("/api/external-product-index")
def upsert_external_product_index(item: ExternalProductIndexUpsertRequest):
    ensure_external_product_index_schema()
    with engine.begin() as conn:
        product = upsert_external_product_index_row(conn, item)
    return {"product": product}


@app.post("/api/external-product-index/bulk")
def bulk_upsert_external_product_index(payload: ExternalProductIndexBulkUpsertRequest):
    ensure_external_product_index_schema()
    products = payload.products or []
    if len(products) > 1000:
        raise HTTPException(status_code=400, detail="Maximaal 1000 externe producten per importverzoek")
    with engine.begin() as conn:
        upserted = [upsert_external_product_index_row(conn, item) for item in products]
    return {"count": len(upserted), "products": upserted}


@app.get("/api/external-product-candidates")
def list_external_product_candidates(
    query: Optional[str] = Query(default=None, max_length=255),
    gtin: Optional[str] = Query(default=None, max_length=32),
    limit: int = Query(default=10, ge=1, le=50),
):
    ensure_external_product_index_schema()
    with engine.begin() as conn:
        candidates = find_external_product_candidates(conn, query=query, gtin=gtin, limit=limit)
    return {
        "candidates": candidates,
        "source": "external_product_index",
        "creates_global_product": False,
        "creates_household_article": False,
    }


@app.get("/api/external-product-index/health")
def external_product_index_health():
    ensure_external_product_index_schema()
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM external_product_index")).scalar() or 0
    return {"status": "ok", "table": "external_product_index", "count": int(count)}


ensure_external_product_index_schema()
