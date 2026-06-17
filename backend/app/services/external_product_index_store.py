from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine


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
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def _sqlite_columns(conn) -> set[str]:
    rows = conn.execute(text("PRAGMA table_info(external_product_index)")).mappings().all()
    return {str(row.get("name") or "") for row in rows}


def _postgres_columns(conn) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'external_product_index'
            """
        )
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _add_missing_columns(conn) -> None:
    dialect_name = str(engine.dialect.name or "").lower()
    existing_columns = _sqlite_columns(conn) if dialect_name == "sqlite" else _postgres_columns(conn)

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


def _fixture_rows() -> list[dict[str, Any]]:
    retailers = [
        ("ah", "Albert Heijn"),
        ("jumbo", "Jumbo"),
        ("lidl", "Lidl"),
        ("aldi", "Aldi"),
        ("plus", "Plus"),
        ("picnic", "Picnic"),
    ]

    products = [
        ("Halfvolle melk", "Zuivel", "1 l", "melk halfvolle zuivel"),
        ("Volle melk", "Zuivel", "1 l", "melk volle zuivel"),
        ("Magere yoghurt", "Zuivel", "1 kg", "yoghurt magere zuivel"),
        ("Jonge kaas 48+", "Kaas", "400 g", "kaas jong plakken blok"),
        ("Volkoren brood", "Brood", "800 g", "brood volkoren"),
        ("Eieren vrije uitloop", "Eieren", "10 stuks", "eieren vrije uitloop"),
        ("Spaghetti", "Pasta", "500 g", "pasta spaghetti"),
        ("Penne rigate", "Pasta", "500 g", "pasta penne"),
        ("Basmati rijst", "Rijst", "1 kg", "rijst basmati"),
        ("Tomatensaus basilicum", "Sauzen", "500 g", "tomatensaus basilicum pasta saus"),
        ("Taco saus mild", "Mexicaans", "230 g", "taco saus mild salsa mexicaans"),
        ("Taco saus hot", "Mexicaans", "230 g", "taco saus hot salsa mexicaans"),
        ("Mexicaanse kruidenmix", "Kruiden", "35 g", "mexicaanse kruidenmix taco burrito fajita"),
        ("Chips paprika", "Snacks", "200 g", "chips paprika aardappelchips"),
        ("Naturel chips", "Snacks", "200 g", "chips naturel aardappelchips"),
        ("Koffie snelfiltermaling", "Koffie", "500 g", "koffie snelfiltermaling"),
        ("Thee earl grey", "Thee", "20 zakjes", "thee earl grey"),
        ("Cola zero", "Frisdrank", "1.5 l", "cola zero frisdrank"),
        ("Mineraalwater bruisend", "Water", "1.5 l", "water bruisend mineraalwater"),
        ("Roomboter ongezouten", "Boter", "250 g", "roomboter ongezouten boter"),
        ("Pindakaas naturel", "Broodbeleg", "350 g", "pindakaas naturel"),
        ("Hagelslag melk", "Broodbeleg", "400 g", "hagelslag melk chocolade"),
        ("Muesli naturel", "Ontbijtgranen", "750 g", "muesli ontbijtgranen"),
        ("Achterham", "Vleeswaren", "150 g", "achterham vleeswaren"),
        ("Kipfilet plakken", "Vleeswaren", "150 g", "kipfilet plakken vleeswaren"),
        ("Bananen", "Fruit", "1 kg", "bananen fruit"),
        ("Elstar appels", "Fruit", "1.5 kg", "appels elstar fruit"),
        ("Spinazie diepvries", "Diepvriesgroente", "450 g", "spinazie diepvries groente"),
        ("Pizza margherita", "Diepvriespizza", "300 g", "pizza margherita diepvries"),
        ("Havermout", "Ontbijtgranen", "500 g", "havermout ontbijt"),
    ]

    brand_by_retailer = {
        "ah": "AH",
        "jumbo": "Jumbo",
        "lidl": "Kania",
        "aldi": "Aldi",
        "plus": "PLUS",
        "picnic": "Picnic",
    }

    rows: list[dict[str, Any]] = []
    timestamp = now_iso()
    base_gtin = 8710000000000

    for retailer_index, (retailer_code, retailer_name) in enumerate(retailers):
        for product_index, (name, category, quantity, tags) in enumerate(products):
            brand = brand_by_retailer[retailer_code]
            gtin = str(base_gtin + retailer_index * 1000 + product_index)
            source_product_code = f"{retailer_code.upper()}-{product_index + 1:05d}"
            product_name = f"{brand} {name}"
            normalized_search_text = normalize_index_text(
                " ".join([
                    retailer_name,
                    retailer_code,
                    brand,
                    product_name,
                    name,
                    category,
                    quantity,
                    tags,
                    gtin,
                    source_product_code,
                ])
            )

            rows.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"rezzerv-off-fixture:{retailer_code}:{source_product_code}")),
                "source_name": "OFF-index",
                "source_product_code": source_product_code,
                "gtin": gtin,
                "ean": gtin,
                "code": gtin,
                "product_name": product_name,
                "brand": brand,
                "brands": brand,
                "quantity": quantity,
                "net_content": quantity,
                "packaging": quantity,
                "category": category,
                "categories": category,
                "image_url": "",
                "source_url": f"https://world.openfoodfacts.org/product/{gtin}",
                "retailer_code": retailer_code,
                "normalized_search_text": normalized_search_text,
                "created_at": timestamp,
                "updated_at": timestamp,
            })

    return rows


def ensure_external_product_index_seeded(minimum_rows: int = 100) -> dict[str, Any]:
    ensure_external_product_index_schema()
    rows = _fixture_rows()

    with engine.begin() as conn:
        existing_count = conn.execute(text("SELECT COUNT(*) AS count FROM external_product_index")).mappings().first()
        count_value = int(existing_count.get("count") or 0)

        if count_value >= minimum_rows:
            return {"ok": True, "seeded": False, "existing_count": count_value}

        dialect_name = str(engine.dialect.name or "").lower()
        inserted = 0

        for row in rows:
            if dialect_name == "sqlite":
                conn.execute(
                    text(
                        """
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
                        """
                    ),
                    row,
                )
            else:
                conn.execute(
                    text(
                        """
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
                        """
                    ),
                    row,
                )
            inserted += 1

    return {"ok": True, "seeded": True, "inserted": inserted}


def search_external_product_index_candidates(receipt_line_text: str, limit: int = 120) -> list[dict[str, Any]]:
    ensure_external_product_index_seeded()

    normalized = normalize_index_text(receipt_line_text)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    if not tokens:
        return []

    params: dict[str, Any] = {"limit": max(10, min(int(limit or 120), 200))}
    where_parts: list[str] = []

    for index, token in enumerate(tokens[:10]):
        key = f"token_{index}"
        where_parts.append(f"normalized_search_text LIKE :{key}")
        params[key] = f"%{token}%"

    where_sql = " OR ".join(where_parts)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM external_product_index
                WHERE {where_sql}
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    return [dict(row) for row in rows]
