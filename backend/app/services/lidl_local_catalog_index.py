from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_taxonomy_store import normalize_taxonomy_text

LIDL_CATALOG_INDEX_SOURCE = "lidl_catalog_index"
LIDL_CATALOG_INDEX_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "lidl_catalog_enrichment_seed.json"

CREATE_EXTERNAL_PRODUCT_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS external_product_index (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_product_code TEXT NOT NULL,
    retailer_code TEXT,
    gtin TEXT,
    product_name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    product_type TEXT,
    quantity_label TEXT,
    search_terms TEXT,
    source_url TEXT,
    confidence_base REAL,
    raw_payload_json TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

EXTERNAL_PRODUCT_INDEX_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "source_name": "TEXT NOT NULL DEFAULT ''",
    "source_product_code": "TEXT NOT NULL DEFAULT ''",
    "retailer_code": "TEXT",
    "gtin": "TEXT",
    "product_name": "TEXT NOT NULL DEFAULT ''",
    "brand": "TEXT",
    "category": "TEXT",
    "product_type": "TEXT",
    "quantity_label": "TEXT",
    "search_terms": "TEXT",
    "source_url": "TEXT",
    "confidence_base": "REAL",
    "raw_payload_json": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _ensure_columns(conn) -> None:
    dialect_name = str(conn.engine.dialect.name or "").lower()
    existing_columns = _sqlite_columns(conn) if dialect_name == "sqlite" else _postgres_columns(conn)
    for column_name, column_definition in EXTERNAL_PRODUCT_INDEX_COLUMNS.items():
        if column_name in existing_columns or column_name == "id":
            continue
        conn.execute(text(f"ALTER TABLE external_product_index ADD COLUMN {column_name} {column_definition}"))


def ensure_external_product_index_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_INDEX_SQL))
        _ensure_columns(conn)
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_external_product_index_source_code
                ON external_product_index (source_name, source_product_code)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_external_product_index_retailer_source
                ON external_product_index (retailer_code, source_name)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_external_product_index_product_name
                ON external_product_index (product_name)
                """
            )
        )


@lru_cache(maxsize=1)
def _load_lidl_catalog_seed_rules() -> tuple[dict[str, Any], ...]:
    if not LIDL_CATALOG_INDEX_SEED_PATH.exists():
        return tuple()
    payload = json.loads(LIDL_CATALOG_INDEX_SEED_PATH.read_text(encoding="utf-8"))
    return tuple(dict(rule) for rule in (payload.get("rules") or []))


def _dedupe_terms(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_taxonomy_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _catalog_index_record(rule: dict[str, Any]) -> dict[str, Any]:
    source_product_code = str(rule.get("source_product_code") or "").strip()
    product_name = str(rule.get("catalog_product_name") or "").strip()
    record_id = f"{LIDL_CATALOG_INDEX_SOURCE}:{source_product_code or uuid.uuid4()}"
    search_terms = _dedupe_terms([
        product_name,
        str(rule.get("brand") or ""),
        str(rule.get("category") or ""),
        str(rule.get("product_type") or ""),
        str(rule.get("quantity_label") or ""),
        *(rule.get("receipt_terms") or []),
        *(rule.get("search_terms") or []),
    ])
    return {
        "id": record_id,
        "source_name": LIDL_CATALOG_INDEX_SOURCE,
        "source_product_code": source_product_code,
        "retailer_code": "lidl",
        "gtin": "",
        "product_name": product_name,
        "brand": str(rule.get("brand") or "").strip(),
        "category": str(rule.get("category") or "").strip(),
        "product_type": str(rule.get("product_type") or "").strip(),
        "quantity_label": str(rule.get("quantity_label") or "").strip(),
        "search_terms": " ".join(search_terms),
        "source_url": str(rule.get("source_url") or "").strip(),
        "confidence_base": float(rule.get("confidence") or 0.0),
        "raw_payload_json": json.dumps(rule, ensure_ascii=False, sort_keys=True),
    }


def ensure_lidl_local_catalog_index() -> dict[str, Any]:
    """Load the local Lidl catalog seed into external_product_index.

    This keeps product knowledge in data/import form. It does not create global products,
    household articles, or inventory events.
    """
    ensure_external_product_index_schema()
    rules = _load_lidl_catalog_seed_rules()
    timestamp = _now_iso()
    written = 0

    with engine.begin() as conn:
        for rule in rules:
            record = _catalog_index_record(rule)
            if not record["source_product_code"] or not record["product_name"]:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO external_product_index (
                        id, source_name, source_product_code, retailer_code, gtin,
                        product_name, brand, category, product_type, quantity_label,
                        search_terms, source_url, confidence_base, raw_payload_json,
                        created_at, updated_at
                    ) VALUES (
                        :id, :source_name, :source_product_code, :retailer_code, :gtin,
                        :product_name, :brand, :category, :product_type, :quantity_label,
                        :search_terms, :source_url, :confidence_base, :raw_payload_json,
                        :created_at, :updated_at
                    )
                    ON CONFLICT(source_name, source_product_code)
                    DO UPDATE SET
                        retailer_code = excluded.retailer_code,
                        gtin = excluded.gtin,
                        product_name = excluded.product_name,
                        brand = excluded.brand,
                        category = excluded.category,
                        product_type = excluded.product_type,
                        quantity_label = excluded.quantity_label,
                        search_terms = excluded.search_terms,
                        source_url = excluded.source_url,
                        confidence_base = excluded.confidence_base,
                        raw_payload_json = excluded.raw_payload_json,
                        updated_at = excluded.updated_at
                    """
                ),
                {**record, "created_at": timestamp, "updated_at": timestamp},
            )
            written += 1

    return {
        "ok": True,
        "source_name": LIDL_CATALOG_INDEX_SOURCE,
        "loaded_count": written,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
