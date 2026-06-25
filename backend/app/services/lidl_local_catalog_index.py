from __future__ import annotations

import difflib
import json
import re
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


def _normalize(value: str | None) -> str:
    normalized = normalize_taxonomy_text(value)
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def _text_similarity(left: str, right: str) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return 0.92
    return difflib.SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in _normalize(left).split() if len(token) >= 3}
    right_tokens = {token for token in _normalize(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _score_catalog_row(receipt_line_text: str, row: dict[str, Any]) -> dict[str, Any]:
    product_name = str(row.get("product_name") or "").strip()
    brand = str(row.get("brand") or "").strip()
    category = str(row.get("category") or "").strip()
    product_type = str(row.get("product_type") or "").strip()
    quantity_label = str(row.get("quantity_label") or "").strip()
    search_terms = str(row.get("search_terms") or "").strip()
    source_product_code = str(row.get("source_product_code") or "").strip()
    confidence_base = float(row.get("confidence_base") or 0.0)

    text_score = max(
        _text_similarity(receipt_line_text, product_name),
        _token_overlap(receipt_line_text, product_name),
        _token_overlap(receipt_line_text, search_terms),
    )
    brand_score = 1.0 if brand and _normalize(brand) in _normalize(receipt_line_text) else (0.70 if brand else 0.45)
    product_type_score = max(_text_similarity(receipt_line_text, product_type), _token_overlap(receipt_line_text, category))
    quantity_score = 0.80 if quantity_label else 0.50
    source_score = max(0.80, min(confidence_base, 0.96))
    variant_score = max(0.70, _token_overlap(receipt_line_text, category))

    breakdown = {
        "text_score": round(text_score, 3),
        "brand_score": round(brand_score, 3),
        "product_type_score": round(product_type_score, 3),
        "quantity_score": round(quantity_score, 3),
        "variant_score": round(variant_score, 3),
        "source_score": round(source_score, 3),
    }
    score = round(
        breakdown["text_score"] * 0.30
        + breakdown["brand_score"] * 0.20
        + breakdown["product_type_score"] * 0.20
        + breakdown["quantity_score"] * 0.10
        + breakdown["variant_score"] * 0.10
        + breakdown["source_score"] * 0.10,
        3,
    )
    candidate_status = "probable_candidate" if score >= 0.85 else "possible_candidate" if score >= 0.70 else "weak_candidate"
    return {
        "candidate_name": product_name or source_product_code or "Onbekend Lidl-catalogusproduct",
        "candidate_brand": brand,
        "candidate_source_name": LIDL_CATALOG_INDEX_SOURCE,
        "candidate_source_product_code": source_product_code or "unknown",
        "source_name": LIDL_CATALOG_INDEX_SOURCE,
        "source_product_code": source_product_code or "unknown",
        "retailer_article_number": source_product_code or "",
        "quantity_label": quantity_label,
        "variant": product_type or category,
        "source_url": str(row.get("source_url") or "").strip(),
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": candidate_status,
        "is_probable": score >= 0.85,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "m2c2i21_lidl_local_catalog_index",
    }


def search_lidl_local_catalog_candidates(receipt_line_text: str, limit: int = 5) -> list[dict[str, Any]]:
    ensure_lidl_local_catalog_index()
    normalized = _normalize(receipt_line_text)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    if not tokens:
        return []

    params: dict[str, Any] = {"source_name": LIDL_CATALOG_INDEX_SOURCE, "retailer_code": "lidl", "limit": 80}
    where_parts: list[str] = []
    search_expr = """
        lower(COALESCE(product_name, '') || ' ' ||
              COALESCE(brand, '') || ' ' ||
              COALESCE(category, '') || ' ' ||
              COALESCE(product_type, '') || ' ' ||
              COALESCE(quantity_label, '') || ' ' ||
              COALESCE(search_terms, '') || ' ' ||
              COALESCE(source_product_code, ''))
    """
    for index, token in enumerate(tokens[:8]):
        key = f"token_{index}"
        where_parts.append(f"{search_expr} LIKE :{key}")
        params[key] = f"%{token}%"

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM external_product_index
                WHERE source_name = :source_name
                  AND retailer_code = :retailer_code
                  AND ({' OR '.join(where_parts)})
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    scored = [_score_catalog_row(receipt_line_text, dict(row)) for row in rows]
    scored.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("candidate_name") or "")))
    return scored[: max(1, min(int(limit or 5), 5))]
