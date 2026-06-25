from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_taxonomy_store import normalize_taxonomy_text
from app.services.retailer_catalog_enrichment import CATALOG_SEED_PATH

ALIAS_SOURCE_NAME = "retailer_alias_learning"
MIN_ALIAS_CONFIDENCE = 0.90

ALIAS_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "retailer_code": "TEXT",
    "normalized_receipt_line_text": "TEXT",
    "raw_receipt_line_text": "TEXT",
    "candidate_source_name": "TEXT",
    "candidate_source_product_code": "TEXT",
    "candidate_name": "TEXT",
    "candidate_brand": "TEXT",
    "category": "TEXT",
    "product_type": "TEXT",
    "quantity_label": "TEXT",
    "source_url": "TEXT",
    "confidence": "REAL",
    "learned_from": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

CREATE_EXTERNAL_PRODUCT_ALIASES_SQL = """
CREATE TABLE IF NOT EXISTS external_product_aliases (
    id TEXT PRIMARY KEY,
    retailer_code TEXT,
    normalized_receipt_line_text TEXT,
    raw_receipt_line_text TEXT,
    candidate_source_name TEXT,
    candidate_source_product_code TEXT,
    candidate_name TEXT,
    candidate_brand TEXT,
    category TEXT,
    product_type TEXT,
    quantity_label TEXT,
    source_url TEXT,
    confidence REAL,
    learned_from TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

CREATE_EXTERNAL_PRODUCT_ALIASES_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_product_aliases_lookup
ON external_product_aliases (retailer_code, normalized_receipt_line_text, candidate_source_name, candidate_source_product_code)
"""

CREATE_EXTERNAL_PRODUCT_ALIASES_CODE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_external_product_aliases_code
ON external_product_aliases (retailer_code, candidate_source_product_code)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_alias_text(value: str | None) -> str:
    return normalize_taxonomy_text(value)


def _sqlite_columns(conn) -> set[str]:
    rows = conn.execute(text("PRAGMA table_info(external_product_aliases)")).mappings().all()
    return {str(row.get("name") or "") for row in rows}


def _postgres_columns(conn) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'external_product_aliases'
            """
        )
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _add_missing_columns(conn) -> None:
    dialect_name = str(engine.dialect.name or "").lower()
    existing_columns = _sqlite_columns(conn) if dialect_name == "sqlite" else _postgres_columns(conn)
    for column_name, column_definition in ALIAS_COLUMNS.items():
        if column_name in existing_columns or column_name == "id":
            continue
        conn.execute(text(f"ALTER TABLE external_product_aliases ADD COLUMN {column_name} {column_definition}"))


def ensure_external_product_aliases_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_ALIASES_SQL))
        _add_missing_columns(conn)
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_ALIASES_INDEX_SQL))
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_ALIASES_CODE_INDEX_SQL))


def _field(mapping: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = mapping.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _candidate_source_name(candidate: dict[str, Any]) -> str:
    return _field(candidate, ["candidate_source_name", "source_name"]) or "external_product_index"


def _candidate_source_code(candidate: dict[str, Any]) -> str:
    return _field(candidate, ["candidate_source_product_code", "source_product_code", "retailer_article_number", "gtin", "ean", "code"])


def _is_usable_source_code(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized) and normalized not in {"unknown", "onbekend", "-"}


def _stem_set(value: str | None) -> set[str]:
    stems: set[str] = set()
    for token in normalize_alias_text(value).split():
        if len(token) >= 4:
            stems.add(token[:5])
    return stems


def _stem_overlap(left: str | None, right: str | None) -> float:
    left_stems = _stem_set(left)
    right_stems = _stem_set(right)
    if not left_stems or not right_stems:
        return 0.0
    return len(left_stems & right_stems) / max(1, len(left_stems | right_stems))


def _alias_candidate(row: dict[str, Any], receipt_line_text: str | None, fuzzy_score: float | None = None) -> dict[str, Any]:
    confidence = float(row.get("confidence") or 0.0)
    if fuzzy_score is not None:
        confidence = min(confidence, max(MIN_ALIAS_CONFIDENCE, round(0.88 + fuzzy_score / 10, 3)))
    score = round(max(MIN_ALIAS_CONFIDENCE, confidence), 3)
    candidate_source_name = str(row.get("candidate_source_name") or ALIAS_SOURCE_NAME).strip()
    candidate_source_product_code = str(row.get("candidate_source_product_code") or "").strip()
    candidate = {
        "candidate_name": str(row.get("candidate_name") or "").strip(),
        "candidate_brand": str(row.get("candidate_brand") or "").strip(),
        "candidate_source_name": ALIAS_SOURCE_NAME,
        "candidate_source_product_code": candidate_source_product_code,
        "source_name": ALIAS_SOURCE_NAME,
        "source_product_code": candidate_source_product_code,
        "retailer_article_number": candidate_source_product_code,
        "quantity_label": str(row.get("quantity_label") or "").strip(),
        "variant": "",
        "source_url": str(row.get("source_url") or "").strip(),
        "score": score,
        "score_breakdown": {
            "retailer_alias_learning": True,
            "alias_source_name": candidate_source_name,
            "alias_confidence": confidence,
            "fuzzy_alias_score": fuzzy_score,
        },
        "candidate_status": "probable_candidate" if score >= 0.85 else "possible_candidate",
        "is_probable": score >= 0.85,
        "created_by": ALIAS_SOURCE_NAME,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
    if receipt_line_text:
        candidate["matched_receipt_line_text"] = str(receipt_line_text).strip()
    return candidate


def _existing_alias(conn, retailer_code: str, normalized_text: str, source_name: str, source_code: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT *
            FROM external_product_aliases
            WHERE retailer_code = :retailer_code
              AND normalized_receipt_line_text = :normalized_text
              AND candidate_source_name = :source_name
              AND candidate_source_product_code = :source_code
            LIMIT 1
            """
        ),
        {
            "retailer_code": retailer_code,
            "normalized_text": normalized_text,
            "source_name": source_name,
            "source_code": source_code,
        },
    ).mappings().first()
    return dict(row) if row else None


def upsert_external_product_alias(
    retailer_code: str | None,
    receipt_line_text: str | None,
    candidate: dict[str, Any],
    learned_from: str,
    confidence: float | None = None,
) -> dict[str, Any]:
    ensure_external_product_aliases_schema()
    normalized_retailer = normalize_alias_text(retailer_code)
    normalized_text = normalize_alias_text(receipt_line_text)
    if not normalized_retailer or not normalized_text:
        return {"ok": False, "reason": "missing_alias_context"}

    source_name = _candidate_source_name(candidate)
    source_code = _candidate_source_code(candidate)
    if not _is_usable_source_code(source_code):
        return {"ok": False, "reason": "missing_source_code"}

    alias_confidence = float(confidence if confidence is not None else candidate.get("score") or 0.0)
    if alias_confidence < MIN_ALIAS_CONFIDENCE:
        return {"ok": False, "reason": "confidence_below_threshold", "confidence": alias_confidence}

    timestamp = now_iso()
    params = {
        "retailer_code": normalized_retailer,
        "normalized_receipt_line_text": normalized_text,
        "raw_receipt_line_text": str(receipt_line_text or "").strip(),
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_code,
        "candidate_name": _field(candidate, ["candidate_name", "product_name", "name"]),
        "candidate_brand": _field(candidate, ["candidate_brand", "brand"]),
        "category": _field(candidate, ["category", "candidate_category"]),
        "product_type": _field(candidate, ["product_type", "candidate_product_type"]),
        "quantity_label": _field(candidate, ["quantity_label", "quantity"]),
        "source_url": _field(candidate, ["source_url", "url"]),
        "confidence": alias_confidence,
        "learned_from": str(learned_from or "retailer_alias_learning").strip(),
        "updated_at": timestamp,
    }

    with engine.begin() as conn:
        existing = _existing_alias(conn, normalized_retailer, normalized_text, source_name, source_code)
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE external_product_aliases
                    SET raw_receipt_line_text = :raw_receipt_line_text,
                        candidate_name = :candidate_name,
                        candidate_brand = :candidate_brand,
                        category = :category,
                        product_type = :product_type,
                        quantity_label = :quantity_label,
                        source_url = :source_url,
                        confidence = CASE WHEN confidence >= :confidence THEN confidence ELSE :confidence END,
                        learned_from = :learned_from,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {**params, "id": existing.get("id")},
            )
            return {"ok": True, "id": existing.get("id"), "updated": True, "created": False}

        alias_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO external_product_aliases (
                    id,
                    retailer_code,
                    normalized_receipt_line_text,
                    raw_receipt_line_text,
                    candidate_source_name,
                    candidate_source_product_code,
                    candidate_name,
                    candidate_brand,
                    category,
                    product_type,
                    quantity_label,
                    source_url,
                    confidence,
                    learned_from,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :retailer_code,
                    :normalized_receipt_line_text,
                    :raw_receipt_line_text,
                    :candidate_source_name,
                    :candidate_source_product_code,
                    :candidate_name,
                    :candidate_brand,
                    :category,
                    :product_type,
                    :quantity_label,
                    :source_url,
                    :confidence,
                    :learned_from,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {**params, "id": alias_id, "created_at": timestamp},
        )
        return {"ok": True, "id": alias_id, "updated": False, "created": True}


def save_alias_from_candidate(
    retailer_code: str | None,
    receipt_line_text: str | None,
    candidate: dict[str, Any],
    learned_from: str = "matchflow_evidence",
    min_score: float = MIN_ALIAS_CONFIDENCE,
) -> dict[str, Any]:
    score = float(candidate.get("score") or 0.0)
    if score < min_score:
        return {"ok": False, "reason": "score_below_threshold", "score": score}
    return upsert_external_product_alias(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        candidate=candidate,
        learned_from=learned_from,
        confidence=score,
    )


def _catalog_rules() -> list[dict[str, Any]]:
    path = Path(CATALOG_SEED_PATH)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [dict(rule) for rule in (payload.get("rules") or [])]


def ensure_catalog_aliases(retailer_code: str | None = "lidl") -> dict[str, Any]:
    normalized_retailer = normalize_alias_text(retailer_code)
    if normalized_retailer != "lidl":
        return {"ok": True, "created_or_updated": 0, "reason": "unsupported_retailer"}

    changed = 0
    for rule in _catalog_rules():
        source_code = str(rule.get("source_product_code") or "").strip()
        if not _is_usable_source_code(source_code):
            continue
        candidate = {
            "candidate_name": str(rule.get("catalog_product_name") or "").strip(),
            "candidate_brand": str(rule.get("brand") or "").strip(),
            "candidate_source_name": "lidl_catalog_enrichment",
            "candidate_source_product_code": source_code,
            "source_url": str(rule.get("source_url") or "").strip(),
            "category": str(rule.get("category") or "").strip(),
            "product_type": str(rule.get("product_type") or "").strip(),
            "quantity_label": str(rule.get("quantity_label") or "").strip(),
            "score": float(rule.get("confidence") or MIN_ALIAS_CONFIDENCE),
        }
        for term in rule.get("receipt_terms") or []:
            result = upsert_external_product_alias(
                retailer_code=normalized_retailer,
                receipt_line_text=str(term or ""),
                candidate=candidate,
                learned_from="catalog_seed",
                confidence=float(rule.get("confidence") or MIN_ALIAS_CONFIDENCE),
            )
            if result.get("ok"):
                changed += 1
    return {"ok": True, "created_or_updated": changed}


def _exact_alias_rows(conn, retailer_code: str, normalized_text: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM external_product_aliases
            WHERE retailer_code = :retailer_code
              AND normalized_receipt_line_text = :normalized_text
            ORDER BY confidence DESC, updated_at DESC
            LIMIT 10
            """
        ),
        {"retailer_code": retailer_code, "normalized_text": normalized_text},
    ).mappings().all()
    return [dict(row) for row in rows]


def _fuzzy_alias_rows(conn, retailer_code: str, normalized_text: str) -> list[tuple[dict[str, Any], float]]:
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM external_product_aliases
            WHERE retailer_code = :retailer_code
              AND confidence >= :min_confidence
            ORDER BY confidence DESC, updated_at DESC
            LIMIT 200
            """
        ),
        {"retailer_code": retailer_code, "min_confidence": MIN_ALIAS_CONFIDENCE},
    ).mappings().all()
    scored: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        item = dict(row)
        overlap = _stem_overlap(normalized_text, str(item.get("normalized_receipt_line_text") or ""))
        if overlap >= 0.65:
            scored.append((item, overlap))
    scored.sort(key=lambda pair: (-pair[1], -float(pair[0].get("confidence") or 0.0)))
    return scored[:5]


def find_alias_candidates(retailer_code: str | None, receipt_line_text: str | None) -> list[dict[str, Any]]:
    ensure_external_product_aliases_schema()
    normalized_retailer = normalize_alias_text(retailer_code)
    normalized_text = normalize_alias_text(receipt_line_text)
    if not normalized_retailer or not normalized_text:
        return []

    ensure_catalog_aliases(normalized_retailer)

    with engine.begin() as conn:
        exact_rows = _exact_alias_rows(conn, normalized_retailer, normalized_text)
        if exact_rows:
            return [_alias_candidate(row, receipt_line_text) for row in exact_rows]

        fuzzy_rows = _fuzzy_alias_rows(conn, normalized_retailer, normalized_text)
        return [_alias_candidate(row, receipt_line_text, fuzzy_score=score) for row, score in fuzzy_rows]
