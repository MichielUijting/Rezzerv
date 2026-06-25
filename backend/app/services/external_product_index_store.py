from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_taxonomy_store import _seed_payload

CATALOG_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "lidl_catalog_enrichment_seed.json"

INDEX_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "source_name": "TEXT",
    "source_product_code": "TEXT",
    "gtin": "TEXT",
    "ean": "TEXT",
    "code": "TEXT",
    "product_name": "TEXT",
    "brand": "TEXT",
    "brands": "TEXT",
    "quantity": "TEXT",
    "net_content": "TEXT",
    "packaging": "TEXT",
    "category": "TEXT",
    "categories": "TEXT",
    "image_url": "TEXT",
    "source_url": "TEXT",
    "retailer_code": "TEXT",
    "normalized_search_text": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

CREATE_EXTERNAL_PRODUCT_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS external_product_index (
    id TEXT PRIMARY KEY,
    source_name TEXT,
    source_product_code TEXT,
    gtin TEXT,
    ean TEXT,
    code TEXT,
    product_name TEXT,
    brand TEXT,
    brands TEXT,
    quantity TEXT,
    net_content TEXT,
    packaging TEXT,
    category TEXT,
    categories TEXT,
    image_url TEXT,
    source_url TEXT,
    retailer_code TEXT,
    normalized_search_text TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_index_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def _sqlite_columns(conn) -> set[str]:
    return {str(row.get("name") or "") for row in conn.execute(text("PRAGMA table_info(external_product_index)")).mappings().all()}


def _postgres_columns(conn) -> set[str]:
    rows = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'external_product_index'")).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _add_missing_columns(conn) -> None:
    existing_columns = _sqlite_columns(conn) if str(engine.dialect.name or "").lower() == "sqlite" else _postgres_columns(conn)
    for column_name, column_definition in INDEX_COLUMNS.items():
        if column_name in existing_columns or column_name == "id":
            continue
        conn.execute(text(f"ALTER TABLE external_product_index ADD COLUMN {column_name} {column_definition}"))


def ensure_external_product_index_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_INDEX_SQL))
        _add_missing_columns(conn)
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_external_product_index_gtin ON external_product_index (gtin)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_external_product_index_source ON external_product_index (source_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_external_product_index_search ON external_product_index (normalized_search_text)"))


def _catalog_payload() -> dict[str, Any]:
    if not CATALOG_SEED_PATH.exists():
        return {"rules": []}
    return json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))


def _json_seed_rows() -> list[dict[str, Any]]:
    timestamp = now_iso()
    rows: list[dict[str, Any]] = []
    retailers = [("lidl", "Lidl")]
    for retailer_code, retailer_name in retailers:
        for index, item in enumerate(_seed_payload().get("taxonomy") or []):
            intent_key = str(item.get("intent_key") or "").strip()
            canonical = str(item.get("canonical_name") or intent_key).strip()
            category = str(item.get("category") or "").strip()
            product_type = str(item.get("product_type") or "").strip()
            synonyms = [str(value or "") for value in (item.get("synonyms") or [])]
            source_product_code = f"{retailer_code}:{intent_key}"
            product_name = f"{retailer_name} {canonical}".strip()
            brand = retailer_name
            normalized_search_text = normalize_index_text(" ".join([
                retailer_name,
                retailer_code,
                brand,
                product_name,
                canonical,
                category,
                product_type,
                intent_key,
                *synonyms,
                source_product_code,
            ]))
            rows.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-taxonomy-index:{retailer_code}:{intent_key}")),
                "source_name": "product_taxonomy_seed",
                "source_product_code": source_product_code,
                "gtin": "",
                "ean": "",
                "code": source_product_code,
                "product_name": product_name,
                "brand": brand,
                "brands": brand,
                "quantity": "",
                "net_content": "",
                "packaging": "",
                "category": category,
                "categories": category,
                "image_url": "",
                "source_url": "",
                "retailer_code": retailer_code,
                "normalized_search_text": normalized_search_text,
                "created_at": timestamp,
                "updated_at": timestamp,
            })
    for rule in _catalog_payload().get("rules") or []:
        source_product_code = str(rule.get("source_product_code") or "").strip()
        if not source_product_code:
            continue
        product_name = str(rule.get("catalog_product_name") or "").strip()
        brand = str(rule.get("brand") or "").strip()
        category = str(rule.get("category") or "").strip()
        quantity = str(rule.get("quantity_label") or "").strip()
        search_terms = [str(value or "") for value in (rule.get("search_terms") or [])]
        normalized_search_text = normalize_index_text(" ".join([
            "lidl",
            brand,
            product_name,
            category,
            quantity,
            source_product_code,
            *search_terms,
        ]))
        rows.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-catalog-index:lidl:{source_product_code}")),
            "source_name": "lidl_catalog_enrichment",
            "source_product_code": source_product_code,
            "gtin": "",
            "ean": "",
            "code": source_product_code,
            "product_name": product_name,
            "brand": brand,
            "brands": brand,
            "quantity": quantity,
            "net_content": quantity,
            "packaging": quantity,
            "category": category,
            "categories": category,
            "image_url": "",
            "source_url": str(rule.get("source_url") or "").strip(),
            "retailer_code": "lidl",
            "normalized_search_text": normalized_search_text,
            "created_at": timestamp,
            "updated_at": timestamp,
        })
    return rows


def ensure_external_product_index_seeded(minimum_rows: int = 1) -> dict[str, Any]:
    ensure_external_product_index_schema()
    rows = _json_seed_rows()
    with engine.begin() as conn:
        dialect_name = str(engine.dialect.name or "").lower()
        inserted = 0
        for row in rows:
            if dialect_name == "sqlite":
                conn.execute(text("""
                    INSERT OR REPLACE INTO external_product_index (
                        id, source_name, source_product_code, gtin, ean, code,
                        product_name, brand, brands, quantity, net_content, packaging,
                        category, categories, image_url, source_url, retailer_code,
                        normalized_search_text, created_at, updated_at
                    ) VALUES (
                        :id, :source_name, :source_product_code, :gtin, :ean, :code,
                        :product_name, :brand, :brands, :quantity, :net_content, :packaging,
                        :category, :categories, :image_url, :source_url, :retailer_code,
                        :normalized_search_text, :created_at, :updated_at
                    )
                """), row)
            else:
                conn.execute(text("""
                    INSERT INTO external_product_index (
                        id, source_name, source_product_code, gtin, ean, code,
                        product_name, brand, brands, quantity, net_content, packaging,
                        category, categories, image_url, source_url, retailer_code,
                        normalized_search_text, created_at, updated_at
                    ) VALUES (
                        :id, :source_name, :source_product_code, :gtin, :ean, :code,
                        :product_name, :brand, :brands, :quantity, :net_content, :packaging,
                        :category, :categories, :image_url, :source_url, :retailer_code,
                        :normalized_search_text, :created_at, :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        source_name = EXCLUDED.source_name,
                        source_product_code = EXCLUDED.source_product_code,
                        product_name = EXCLUDED.product_name,
                        brand = EXCLUDED.brand,
                        quantity = EXCLUDED.quantity,
                        category = EXCLUDED.category,
                        normalized_search_text = EXCLUDED.normalized_search_text,
                        updated_at = EXCLUDED.updated_at
                """), row)
            inserted += 1
    return {"ok": True, "seeded": True, "inserted": inserted, "source": "json_seed"}


def search_external_product_index_candidates(
    receipt_line_text: str,
    limit: int = 120,
    retailer_code: str | None = None,
    additional_search_terms: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    ensure_external_product_index_seeded()
    normalized = normalize_index_text(receipt_line_text)
    search_text = " ".join([normalized, *[normalize_index_text(term) for term in (additional_search_terms or [])]])
    tokens: list[str] = []
    seen_tokens: set[str] = set()
    for token in search_text.split():
        if len(token) < 3 or token in seen_tokens:
            continue
        tokens.append(token)
        seen_tokens.add(token)
    if not tokens:
        return []
    params: dict[str, Any] = {"limit": max(10, min(int(limit or 120), 200))}
    where_parts: list[str] = []
    for index, token in enumerate(tokens[:16]):
        key = f"token_{index}"
        where_parts.append(f"normalized_search_text LIKE :{key}")
        params[key] = f"%{token}%"
    retailer_filter_sql = ""
    normalized_retailer = normalize_index_text(retailer_code)
    if normalized_retailer:
        params["retailer_code"] = normalized_retailer
        retailer_filter_sql = " AND (COALESCE(retailer_code, '') = :retailer_code OR COALESCE(retailer_code, '') = '')"
    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT *
            FROM external_product_index
            WHERE ({' OR '.join(where_parts)}){retailer_filter_sql}
            LIMIT :limit
        """), params).mappings().all()
    return [dict(row) for row in rows]
