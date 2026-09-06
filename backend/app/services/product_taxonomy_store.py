from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine

TAXONOMY_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "product_taxonomy_seed.json"

_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "product_taxonomy": {
        "intent_key",
        "canonical_name",
        "category",
        "product_type",
        "parent_intent_key",
        "default_base_unit",
        "is_active",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    },
    "product_taxonomy_synonyms": {
        "id",
        "intent_key",
        "synonym",
        "normalized_synonym",
        "priority",
        "is_active",
        "source",
    },
    "retailer_receipt_terms": {
        "id",
        "retailer_code",
        "receipt_term",
        "normalized_receipt_term",
        "normalized_term",
        "intent_key",
        "confidence",
        "is_active",
        "source",
    },
}

_REQUIRED_INDEXES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ux_product_taxonomy_intent_key": ("product_taxonomy", ("intent_key",), True),
    "idx_product_taxonomy_synonyms_norm": (
        "product_taxonomy_synonyms",
        ("normalized_synonym",),
        False,
    ),
    "idx_product_taxonomy_synonyms_intent": (
        "product_taxonomy_synonyms",
        ("intent_key",),
        False,
    ),
    "idx_retailer_receipt_terms_norm": (
        "retailer_receipt_terms",
        ("retailer_code", "normalized_receipt_term"),
        False,
    ),
    "idx_retailer_receipt_terms_intent": (
        "retailer_receipt_terms",
        ("intent_key",),
        False,
    ),
}


def normalize_taxonomy_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def contains_taxonomy_term(normalized_text: str, normalized_term: str) -> bool:
    if not normalized_text or not normalized_term:
        return False

    text_tokens = normalized_text.split()
    term_tokens = normalized_term.split()

    if len(term_tokens) == 1:
        term = term_tokens[0]
        return term in text_tokens or normalized_text == term

    for index in range(0, len(text_tokens) - len(term_tokens) + 1):
        if text_tokens[index:index + len(term_tokens)] == term_tokens:
            return True

    return False


def _seed_payload() -> dict[str, Any]:
    if not TAXONOMY_SEED_PATH.exists():
        return {"taxonomy": [], "retailer_receipt_terms": [], "product_variant_terms": []}
    return json.loads(TAXONOMY_SEED_PATH.read_text(encoding="utf-8"))


def ensure_product_taxonomy_schema() -> None:
    """Validate the Alembic-owned taxonomy schema without mutating it."""
    with engine.connect() as conn:
        inspector = inspect(conn)
        for table_name, required_columns in _REQUIRED_COLUMNS.items():
            if not inspector.has_table(table_name):
                raise RuntimeError(
                    f"Canonical product taxonomy schema ontbreekt: tabel {table_name}. "
                    "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
                )
            actual_columns = {
                str(column.get("name") or "")
                for column in inspector.get_columns(table_name)
            }
            missing = required_columns - actual_columns
            if missing:
                raise RuntimeError(
                    f"Canonical product taxonomy schema wijkt af: {table_name} mist "
                    f"{sorted(missing)}. Voer Alembic migrations uit."
                )

        for index_name, (table_name, expected_columns, expected_unique) in _REQUIRED_INDEXES.items():
            indexes = {
                str(index.get("name") or ""): index
                for index in inspector.get_indexes(table_name)
            }
            index = indexes.get(index_name)
            actual_columns = tuple(
                str(column or "") for column in ((index or {}).get("column_names") or ())
            )
            if (
                index is None
                or actual_columns != expected_columns
                or bool(index.get("unique")) != expected_unique
            ):
                raise RuntimeError(
                    f"Canonical product taxonomy index wijkt af: {index_name}; "
                    f"expected={expected_columns!r}/{expected_unique}, "
                    f"actual={actual_columns!r}/{bool((index or {}).get('unique'))}."
                )


def _upsert_taxonomy_row(conn, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO product_taxonomy (
                intent_key, canonical_name, category, product_type, parent_intent_key,
                is_active, created_by, updated_by
            ) VALUES (
                :intent_key, :canonical_name, :category, :product_type, :parent_intent_key,
                TRUE, :created_by, :updated_by
            )
            ON CONFLICT (intent_key) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                category = excluded.category,
                product_type = excluded.product_type,
                parent_intent_key = excluded.parent_intent_key,
                is_active = TRUE,
                updated_by = excluded.updated_by
            """
        ),
        row,
    )


def _upsert_synonym_row(conn, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO product_taxonomy_synonyms (
                id, intent_key, synonym, normalized_synonym, priority, is_active, source
            ) VALUES (
                :id, :intent_key, :synonym, :normalized_synonym, :priority, TRUE, :source
            )
            ON CONFLICT (id) DO UPDATE SET
                synonym = excluded.synonym,
                normalized_synonym = excluded.normalized_synonym,
                priority = excluded.priority,
                is_active = TRUE,
                source = excluded.source
            """
        ),
        row,
    )


def _upsert_retailer_term_row(conn, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO retailer_receipt_terms (
                id, retailer_code, receipt_term, normalized_receipt_term, normalized_term,
                intent_key, confidence, is_active, source
            ) VALUES (
                :id, :retailer_code, :receipt_term, :normalized_receipt_term, :normalized_term,
                :intent_key, :confidence, TRUE, :source
            )
            ON CONFLICT (id) DO UPDATE SET
                receipt_term = excluded.receipt_term,
                normalized_receipt_term = excluded.normalized_receipt_term,
                normalized_term = excluded.normalized_term,
                intent_key = excluded.intent_key,
                confidence = excluded.confidence,
                is_active = TRUE,
                source = excluded.source
            """
        ),
        row,
    )


def ensure_product_taxonomy_seeded() -> dict[str, Any]:
    ensure_product_taxonomy_schema()
    payload = _seed_payload()
    taxonomy_rows = payload.get("taxonomy") or []
    retailer_rows = payload.get("retailer_receipt_terms") or []

    inserted_taxonomy = 0
    inserted_synonyms = 0
    inserted_retailer_terms = 0

    with engine.begin() as conn:
        for item in taxonomy_rows:
            intent_key = str(item.get("intent_key") or "").strip()
            if not intent_key:
                continue
            taxonomy_row = {
                "intent_key": intent_key,
                "canonical_name": str(item.get("canonical_name") or intent_key).strip(),
                "category": str(item.get("category") or "").strip(),
                "product_type": str(item.get("product_type") or "").strip(),
                "parent_intent_key": str(item.get("parent_intent_key") or "").strip() or None,
                "created_by": "m2c2i9_seed",
                "updated_by": "m2c2i9_seed",
            }
            _upsert_taxonomy_row(conn, taxonomy_row)
            inserted_taxonomy += 1

            terms = [taxonomy_row["canonical_name"], *(item.get("synonyms") or [])]
            seen_terms: set[str] = set()
            for priority_offset, synonym in enumerate(terms):
                synonym_text = str(synonym or "").strip()
                normalized = normalize_taxonomy_text(synonym_text)
                if not normalized or normalized in seen_terms:
                    continue
                seen_terms.add(normalized)
                synonym_row = {
                    "id": f"{intent_key}:{normalized}",
                    "intent_key": intent_key,
                    "synonym": synonym_text,
                    "normalized_synonym": normalized,
                    "priority": max(1, 1000 - priority_offset),
                    "source": "m2c2i9_seed",
                }
                _upsert_synonym_row(conn, synonym_row)
                inserted_synonyms += 1

        for item in retailer_rows:
            retailer_code = normalize_taxonomy_text(item.get("retailer_code"))
            receipt_term = str(item.get("receipt_term") or "").strip()
            normalized_receipt_term = normalize_taxonomy_text(receipt_term)
            intent_key = str(item.get("intent_key") or "").strip()
            if not retailer_code or not normalized_receipt_term or not intent_key:
                continue
            row = {
                "id": f"{retailer_code}:{normalized_receipt_term}:{intent_key}",
                "retailer_code": retailer_code,
                "receipt_term": receipt_term,
                "normalized_receipt_term": normalized_receipt_term,
                "normalized_term": normalize_taxonomy_text(item.get("normalized_term")),
                "intent_key": intent_key,
                "confidence": float(item.get("confidence") or 1.0),
                "source": str(item.get("source") or "m2c2i9_seed"),
            }
            _upsert_retailer_term_row(conn, row)
            inserted_retailer_terms += 1

    load_taxonomy_rules.cache_clear()
    load_taxonomy_metadata.cache_clear()
    load_product_variant_terms.cache_clear()
    return {
        "ok": True,
        "taxonomy_rows": inserted_taxonomy,
        "synonym_rows": inserted_synonyms,
        "retailer_receipt_term_rows": inserted_retailer_terms,
    }


def _fallback_rules_from_seed(retailer_code: str | None = None) -> list[dict[str, Any]]:
    payload = _seed_payload()
    rules: list[dict[str, Any]] = []
    for item in payload.get("taxonomy") or []:
        intent_key = str(item.get("intent_key") or "").strip()
        terms = [item.get("canonical_name"), *(item.get("synonyms") or [])]
        for priority_offset, term in enumerate(terms):
            normalized = normalize_taxonomy_text(term)
            if normalized and intent_key:
                rules.append({
                    "intent_key": intent_key,
                    "normalized_term": normalized,
                    "priority": max(1, 1000 - priority_offset),
                    "source": "seed_file",
                })
    for item in payload.get("retailer_receipt_terms") or []:
        item_retailer = normalize_taxonomy_text(item.get("retailer_code"))
        if retailer_code and item_retailer != normalize_taxonomy_text(retailer_code):
            continue
        normalized = normalize_taxonomy_text(item.get("receipt_term"))
        intent_key = str(item.get("intent_key") or "").strip()
        if normalized and intent_key:
            rules.append({
                "intent_key": intent_key,
                "normalized_term": normalized,
                "priority": 1200,
                "source": "retailer_seed_file",
            })
    return _sort_taxonomy_rules(rules)


def _sort_taxonomy_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rules,
        key=lambda row: (
            -int(row.get("priority") or 0),
            -len(str(row.get("normalized_term") or "").split()),
            -len(str(row.get("normalized_term") or "")),
            str(row.get("normalized_term") or ""),
        ),
    )


@lru_cache(maxsize=32)
def load_taxonomy_rules(retailer_code: str | None = None) -> tuple[dict[str, Any], ...]:
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    try:
        ensure_product_taxonomy_seeded()
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT intent_key, normalized_synonym AS normalized_term, priority, source
                    FROM product_taxonomy_synonyms
                    WHERE COALESCE(is_active, TRUE) = TRUE

                    UNION ALL

                    SELECT intent_key, normalized_receipt_term AS normalized_term, 1200 AS priority, source
                    FROM retailer_receipt_terms
                    WHERE COALESCE(is_active, TRUE) = TRUE
                      AND (:retailer_code = '' OR retailer_code = :retailer_code)
                    """
                ),
                {"retailer_code": normalized_retailer},
            ).mappings().all()
        return tuple(_sort_taxonomy_rules([dict(row) for row in rows]))
    except Exception:
        return tuple(_fallback_rules_from_seed(normalized_retailer or None))


def classify_product_intent_from_taxonomy(text_value: str | None, retailer_code: str | None = None) -> str:
    normalized = normalize_taxonomy_text(text_value)
    if not normalized:
        return ""

    for rule in load_taxonomy_rules(retailer_code):
        normalized_term = str(rule.get("normalized_term") or "")
        if contains_taxonomy_term(normalized, normalized_term):
            return str(rule.get("intent_key") or "")

    return ""


def _fallback_metadata_from_seed() -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for item in _seed_payload().get("taxonomy") or []:
        intent_key = str(item.get("intent_key") or "").strip()
        if not intent_key:
            continue
        metadata[intent_key] = {
            "intent_key": intent_key,
            "canonical_name": str(item.get("canonical_name") or intent_key).strip(),
            "category": normalize_taxonomy_text(item.get("category")),
            "product_type": normalize_taxonomy_text(item.get("product_type")),
        }
    return metadata


@lru_cache(maxsize=1)
def load_taxonomy_metadata() -> dict[str, dict[str, str]]:
    try:
        ensure_product_taxonomy_seeded()
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT intent_key, canonical_name, category, product_type
                    FROM product_taxonomy
                    WHERE COALESCE(is_active, TRUE) = TRUE
                    """
                )
            ).mappings().all()
        return {
            str(row["intent_key"]): {
                "intent_key": str(row["intent_key"]),
                "canonical_name": str(row["canonical_name"] or row["intent_key"]),
                "category": normalize_taxonomy_text(row["category"]),
                "product_type": normalize_taxonomy_text(row["product_type"]),
            }
            for row in rows
            if row.get("intent_key")
        }
    except Exception:
        return _fallback_metadata_from_seed()


def get_taxonomy_metadata_for_intent(intent_key: str | None) -> dict[str, str]:
    key = str(intent_key or "").strip()
    if not key:
        return {"intent_key": "", "canonical_name": "", "category": "", "product_type": ""}
    return load_taxonomy_metadata().get(
        key,
        {"intent_key": key, "canonical_name": key, "category": "", "product_type": ""},
    )


def _variant_rules_from_seed(intent_key: str | None = None) -> list[dict[str, Any]]:
    requested_intent = str(intent_key or "").strip()
    rules: list[dict[str, Any]] = []
    for item in _seed_payload().get("product_variant_terms") or []:
        item_intent = str(item.get("intent_key") or "").strip()
        if requested_intent and item_intent != requested_intent:
            continue
        variant_term = str(item.get("variant_term") or "").strip()
        normalized_variant = normalize_taxonomy_text(variant_term)
        if not item_intent or not normalized_variant:
            continue
        search_terms = [
            normalize_taxonomy_text(search_term)
            for search_term in (item.get("search_terms") or [])
            if normalize_taxonomy_text(search_term)
        ]
        rules.append({
            "intent_key": item_intent,
            "variant_term": variant_term,
            "normalized_variant_term": normalized_variant,
            "variant_type": normalize_taxonomy_text(item.get("variant_type")),
            "search_terms": search_terms,
            "confidence": float(item.get("confidence") or 1.0),
            "source": str(item.get("source") or "taxonomy_seed"),
        })
    return sorted(
        rules,
        key=lambda row: (
            -len(str(row.get("normalized_variant_term") or "").split()),
            -len(str(row.get("normalized_variant_term") or "")),
            str(row.get("normalized_variant_term") or ""),
        ),
    )


@lru_cache(maxsize=64)
def load_product_variant_terms(intent_key: str | None = None) -> tuple[dict[str, Any], ...]:
    return tuple(_variant_rules_from_seed(intent_key))
