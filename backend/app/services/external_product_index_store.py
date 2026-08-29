from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.product_taxonomy_store import _seed_payload

CATALOG_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "lidl_catalog_enrichment_seed.json"

# M2C2i24S-c: taxonomie-indexrijen zijn generiek per ondersteunde retailer.
# Productbetekenis komt uit de taxonomie-data, niet uit Python-artikelregels.
TAXONOMY_INDEX_RETAILERS: tuple[tuple[str, str], ...] = (
    ("lidl", "Lidl"),
    ("jumbo", "Jumbo"),
    ("albert heijn", "Albert Heijn"),
    ("aldi", "Aldi"),
    ("plus", "PLUS"),
)

_REQUIRED_INDEX_COLUMNS = {
    "id",
    "source_name",
    "source_product_code",
    "gtin",
    "ean",
    "code",
    "product_name",
    "brand",
    "brands",
    "quantity",
    "net_content",
    "packaging",
    "category",
    "categories",
    "image_url",
    "source_url",
    "retailer_code",
    "normalized_search_text",
    "created_at",
    "updated_at",
}
_REQUIRED_INDEXES = {
    "idx_external_product_index_gtin": ("gtin",),
    "idx_external_product_index_source": ("source_name",),
    "idx_external_product_index_search": ("normalized_search_text",),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_index_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def ensure_external_product_index_schema() -> None:
    """Validate the Alembic-owned external product index contract; never mutate schema."""
    inspector = inspect(engine)
    if not inspector.has_table("external_product_index"):
        raise RuntimeError("external_product_index ontbreekt; voer Alembic migrations uit")
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("external_product_index")
    }
    missing = _REQUIRED_INDEX_COLUMNS - columns
    if missing:
        raise RuntimeError(
            "external_product_index schema incompleet: "
            f"missing={sorted(missing)}"
        )
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes("external_product_index")
    }
    for index_name, expected_columns in _REQUIRED_INDEXES.items():
        index = indexes.get(index_name)
        if not index or tuple(index.get("column_names") or ()) != expected_columns:
            raise RuntimeError(
                "external_product_index indexcontract incompleet: "
                f"{index_name}"
            )


def _catalog_payload() -> dict[str, Any]:
    if not CATALOG_SEED_PATH.exists():
        return {"rules": []}
    return json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))


def _taxonomy_index_row(
    retailer_code: str,
    retailer_name: str,
    item: dict[str, Any],
    timestamp: str,
) -> dict[str, Any] | None:
    intent_key = str(item.get("intent_key") or "").strip()
    if not intent_key:
        return None

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
    return {
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
    }


def _json_seed_rows() -> list[dict[str, Any]]:
    timestamp = now_iso()
    rows: list[dict[str, Any]] = []
    for retailer_code, retailer_name in TAXONOMY_INDEX_RETAILERS:
        for item in _seed_payload().get("taxonomy") or []:
            row = _taxonomy_index_row(retailer_code, retailer_name, item, timestamp)
            if row:
                rows.append(row)

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
    del minimum_rows
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
                        retailer_code = EXCLUDED.retailer_code,
                        normalized_search_text = EXCLUDED.normalized_search_text,
                        updated_at = EXCLUDED.updated_at
                """), row)
            inserted += 1
    return {
        "ok": True,
        "seeded": True,
        "inserted": inserted,
        "source": "json_seed",
        "taxonomy_index_retailers": [retailer_code for retailer_code, _ in TAXONOMY_INDEX_RETAILERS],
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


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
