from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine


PRODUCT_TAXONOMY_SQL = """
CREATE TABLE IF NOT EXISTS product_taxonomy (
    id TEXT PRIMARY KEY,
    intent_key TEXT UNIQUE NOT NULL,
    canonical_name TEXT NOT NULL,
    category TEXT,
    product_type TEXT,
    default_base_unit TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""

PRODUCT_TAXONOMY_TERMS_SQL = """
CREATE TABLE IF NOT EXISTS product_taxonomy_terms (
    id TEXT PRIMARY KEY,
    intent_key TEXT NOT NULL,
    term TEXT NOT NULL,
    term_type TEXT,
    language TEXT DEFAULT 'nl',
    confidence REAL DEFAULT 1.0,
    source TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""

PRODUCT_INVENTORY_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS product_inventory_groups (
    inventory_group_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    default_base_unit TEXT NOT NULL,
    aggregation_mode TEXT DEFAULT 'sum_quantity',
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""

PRODUCT_GROUP_MEMBERSHIPS_SQL = """
CREATE TABLE IF NOT EXISTS product_group_memberships (
    id TEXT PRIMARY KEY,
    global_product_id TEXT NOT NULL,
    inventory_group_key TEXT NOT NULL,
    comparison_group_key TEXT,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    confirmed_by_user INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""

PRODUCT_UNIT_CONVERSIONS_SQL = """
CREATE TABLE IF NOT EXISTS product_unit_conversions (
    id TEXT PRIMARY KEY,
    global_product_id TEXT NOT NULL,
    inventory_group_key TEXT,
    content_value REAL,
    content_unit TEXT,
    base_quantity REAL,
    base_unit TEXT,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

GROUP_MEMBERSHIP_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_group_memberships_product
ON product_group_memberships (global_product_id, inventory_group_key)
"""

TAXONOMY_TERM_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_taxonomy_terms_intent
ON product_taxonomy_terms (intent_key, active)
"""

SCHEMA_COLUMNS: dict[str, dict[str, str]] = {
    "product_taxonomy": {
        "id": "TEXT",
        "intent_key": "TEXT",
        "canonical_name": "TEXT",
        "category": "TEXT",
        "product_type": "TEXT",
        "default_base_unit": "TEXT",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "product_taxonomy_terms": {
        "id": "TEXT",
        "intent_key": "TEXT",
        "term": "TEXT",
        "term_type": "TEXT",
        "language": "TEXT DEFAULT 'nl'",
        "confidence": "REAL DEFAULT 1.0",
        "source": "TEXT",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "product_inventory_groups": {
        "inventory_group_key": "TEXT",
        "display_name": "TEXT",
        "default_base_unit": "TEXT",
        "aggregation_mode": "TEXT DEFAULT 'sum_quantity'",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "product_group_memberships": {
        "id": "TEXT",
        "global_product_id": "TEXT",
        "inventory_group_key": "TEXT",
        "comparison_group_key": "TEXT",
        "confidence": "REAL DEFAULT 1.0",
        "source": "TEXT",
        "confirmed_by_user": "INTEGER DEFAULT 0",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "product_unit_conversions": {
        "id": "TEXT",
        "global_product_id": "TEXT",
        "inventory_group_key": "TEXT",
        "content_value": "REAL",
        "content_unit": "TEXT",
        "base_quantity": "REAL",
        "base_unit": "TEXT",
        "confidence": "REAL DEFAULT 1.0",
        "source": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
}

DEFAULT_TAXONOMY = [
    {
        "intent_key": "groente.courgette",
        "canonical_name": "Courgette",
        "category": "Groente",
        "product_type": "Verse groente",
        "default_base_unit": "kg",
        "terms": ["courgette", "zucchini"],
    },
    {
        "intent_key": "drank.wijn.rood",
        "canonical_name": "Rode wijn",
        "category": "Drank",
        "product_type": "Wijn",
        "default_base_unit": "l",
        "terms": ["rode wijn", "red wine", "rouge", "vino rosso"],
    },
    {
        "intent_key": "zuivel.melk.halfvol",
        "canonical_name": "Halfvolle melk",
        "category": "Zuivel",
        "product_type": "Melk",
        "default_base_unit": "l",
        "terms": ["halfvolle melk", "halfvol melk", "melk halfvol"],
    },
    {
        "intent_key": "saus.mosterd",
        "canonical_name": "Mosterd",
        "category": "Saus",
        "product_type": "Mosterd",
        "default_base_unit": "kg",
        "terms": ["mosterd", "mustard"],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("ë", "e").replace("é", "e").replace("è", "e").replace("ï", "i")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _get_columns(conn, table_name: str) -> set[str]:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}
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


def _ensure_missing_columns(conn, table_name: str) -> None:
    existing_columns = _get_columns(conn, table_name)
    expected_columns = SCHEMA_COLUMNS.get(table_name, {})
    for column_name, column_definition in expected_columns.items():
        if column_name in existing_columns:
            continue
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))


def _ensure_row_ids(conn, table_name: str) -> None:
    columns = _get_columns(conn, table_name)
    if "id" not in columns:
        return
    rows = conn.execute(text(f"SELECT rowid FROM {table_name} WHERE id IS NULL OR trim(id) = ''")).mappings().all()
    for row in rows:
        conn.execute(
            text(f"UPDATE {table_name} SET id = :id WHERE rowid = :rowid"),
            {"id": str(uuid.uuid4()), "rowid": row.get("rowid")},
        )


def ensure_product_inventory_group_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(PRODUCT_TAXONOMY_SQL))
        conn.execute(text(PRODUCT_TAXONOMY_TERMS_SQL))
        conn.execute(text(PRODUCT_INVENTORY_GROUPS_SQL))
        conn.execute(text(PRODUCT_GROUP_MEMBERSHIPS_SQL))
        conn.execute(text(PRODUCT_UNIT_CONVERSIONS_SQL))
        for table_name in SCHEMA_COLUMNS:
            _ensure_missing_columns(conn, table_name)
            _ensure_row_ids(conn, table_name)
        conn.execute(text(GROUP_MEMBERSHIP_INDEX_SQL))
        conn.execute(text(TAXONOMY_TERM_INDEX_SQL))
        seed_default_inventory_groups(conn)


def _row_exists(conn, sql: str, params: dict[str, Any]) -> bool:
    return conn.execute(text(sql), params).mappings().first() is not None


def seed_default_inventory_groups(conn) -> None:
    timestamp = now_iso()
    for item in DEFAULT_TAXONOMY:
        intent_key = item["intent_key"]
        if not _row_exists(conn, "SELECT 1 FROM product_taxonomy WHERE intent_key = :intent_key LIMIT 1", {"intent_key": intent_key}):
            conn.execute(
                text(
                    """
                    INSERT INTO product_taxonomy (id, intent_key, canonical_name, category, product_type, default_base_unit, active, created_at, updated_at)
                    VALUES (:id, :intent_key, :canonical_name, :category, :product_type, :default_base_unit, 1, :created_at, :updated_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "intent_key": intent_key,
                    "canonical_name": item["canonical_name"],
                    "category": item["category"],
                    "product_type": item["product_type"],
                    "default_base_unit": item["default_base_unit"],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE product_taxonomy
                    SET canonical_name = COALESCE(NULLIF(canonical_name, ''), :canonical_name),
                        category = COALESCE(NULLIF(category, ''), :category),
                        product_type = COALESCE(NULLIF(product_type, ''), :product_type),
                        default_base_unit = COALESCE(NULLIF(default_base_unit, ''), :default_base_unit),
                        active = COALESCE(active, 1),
                        updated_at = :updated_at
                    WHERE intent_key = :intent_key
                    """
                ),
                {
                    "intent_key": intent_key,
                    "canonical_name": item["canonical_name"],
                    "category": item["category"],
                    "product_type": item["product_type"],
                    "default_base_unit": item["default_base_unit"],
                    "updated_at": timestamp,
                },
            )

        if not _row_exists(conn, "SELECT 1 FROM product_inventory_groups WHERE inventory_group_key = :key LIMIT 1", {"key": intent_key}):
            conn.execute(
                text(
                    """
                    INSERT INTO product_inventory_groups (inventory_group_key, display_name, default_base_unit, aggregation_mode, active, created_at, updated_at)
                    VALUES (:inventory_group_key, :display_name, :default_base_unit, 'sum_quantity', 1, :created_at, :updated_at)
                    """
                ),
                {
                    "inventory_group_key": intent_key,
                    "display_name": item["canonical_name"],
                    "default_base_unit": item["default_base_unit"],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE product_inventory_groups
                    SET display_name = COALESCE(NULLIF(display_name, ''), :display_name),
                        default_base_unit = COALESCE(NULLIF(default_base_unit, ''), :default_base_unit),
                        aggregation_mode = COALESCE(NULLIF(aggregation_mode, ''), 'sum_quantity'),
                        active = COALESCE(active, 1),
                        updated_at = :updated_at
                    WHERE inventory_group_key = :inventory_group_key
                    """
                ),
                {
                    "inventory_group_key": intent_key,
                    "display_name": item["canonical_name"],
                    "default_base_unit": item["default_base_unit"],
                    "updated_at": timestamp,
                },
            )

        for term_value in item["terms"]:
            normalized_term = normalize_text(term_value)
            if not _row_exists(
                conn,
                """
                SELECT 1 FROM product_taxonomy_terms
                WHERE intent_key = :intent_key AND lower(term) = lower(:term)
                LIMIT 1
                """,
                {"intent_key": intent_key, "term": normalized_term},
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO product_taxonomy_terms (id, intent_key, term, term_type, language, confidence, source, active, created_at, updated_at)
                        VALUES (:id, :intent_key, :term, 'seed', 'nl', 1.0, 'm2c2i30a_seed', 1, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "intent_key": intent_key,
                        "term": normalized_term,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                )


def _inventory_rows(conn, household_id: str | None = None) -> list[dict[str, Any]]:
    columns = _get_columns(conn, "inventory")
    if not columns:
        return []

    select_columns = ["i.id", "i.naam AS product_name", "i.aantal AS stock_quantity"]
    select_columns.append("i.household_id" if "household_id" in columns else "NULL AS household_id")
    select_columns.append("i.household_article_id" if "household_article_id" in columns else "NULL AS household_article_id")
    if "space_id" in columns:
        select_columns.append("s.naam AS location_name")
        join_space = "LEFT JOIN spaces s ON s.id = i.space_id"
    else:
        select_columns.append("NULL AS location_name")
        join_space = ""
    if "sublocation_id" in columns:
        select_columns.append("sl.naam AS sublocation_name")
        join_sublocation = "LEFT JOIN sublocations sl ON sl.id = i.sublocation_id"
    else:
        select_columns.append("NULL AS sublocation_name")
        join_sublocation = ""

    where_parts = ["COALESCE(i.status, 'active') = 'active'"] if "status" in columns else ["1 = 1"]
    params: dict[str, Any] = {}
    if household_id and "household_id" in columns:
        where_parts.append("COALESCE(i.household_id, '') = COALESCE(:household_id, '')")
        params["household_id"] = household_id

    rows = conn.execute(
        text(
            f"""
            SELECT {', '.join(select_columns)}
            FROM inventory i
            {join_space}
            {join_sublocation}
            WHERE {' AND '.join(where_parts)}
            ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _taxonomy_terms(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT
                t.intent_key,
                t.term,
                COALESCE(t.confidence, 1.0) AS term_confidence,
                g.display_name,
                g.default_base_unit
            FROM product_taxonomy_terms t
            JOIN product_inventory_groups g ON g.inventory_group_key = t.intent_key
            WHERE COALESCE(t.active, 1) = 1
              AND COALESCE(g.active, 1) = 1
            ORDER BY length(t.term) DESC, t.term ASC
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _match_inventory_group(item_name: str, terms: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_name = normalize_text(item_name)
    if not normalized_name:
        return None
    padded_name = f" {normalized_name} "
    for term in terms:
        normalized_term = normalize_text(term.get("term"))
        if normalized_term and f" {normalized_term} " in padded_name:
            return term
    return None


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except Exception:
        return None


def infer_normalized_quantity(product_name: str, stock_quantity: float, base_unit: str) -> tuple[float | None, str, str, float]:
    normalized_name = normalize_text(product_name)
    quantity = float(stock_quantity or 0)
    unit = str(base_unit or "stuk").strip().lower() or "stuk"

    unit_matches = re.findall(r"(\d+(?:[\.,]\d+)?)\s*(kg|kilo|g|gram|l|liter|ml|cl)\b", normalized_name)
    if not unit_matches:
        return None, unit, "missing_unit_conversion", 0.25

    value, source_unit = unit_matches[-1]
    parsed_value = _parse_number(value)
    if parsed_value is None:
        return None, unit, "invalid_unit_expression", 0.25

    source_unit = source_unit.lower()
    if source_unit in {"kg", "kilo"}:
        converted_value, converted_unit = parsed_value, "kg"
    elif source_unit in {"g", "gram"}:
        converted_value, converted_unit = parsed_value / 1000.0, "kg"
    elif source_unit in {"l", "liter"}:
        converted_value, converted_unit = parsed_value, "l"
    elif source_unit == "cl":
        converted_value, converted_unit = parsed_value / 100.0, "l"
    elif source_unit == "ml":
        converted_value, converted_unit = parsed_value / 1000.0, "l"
    else:
        return None, unit, "unsupported_unit", 0.25

    if converted_unit != unit:
        return None, unit, "unit_mismatch", 0.25
    return converted_value * quantity, unit, "parsed_from_product_name", 0.75


def list_inventory_groups(household_id: str | None = None) -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        terms = _taxonomy_terms(conn)
        inventory_rows = _inventory_rows(conn, household_id=household_id)

    grouped: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for row in inventory_rows:
        product_name = str(row.get("product_name") or "").strip()
        quantity = float(row.get("stock_quantity") or 0)
        match = _match_inventory_group(product_name, terms)
        if not match:
            unresolved.append({
                "inventory_id": str(row.get("id") or ""),
                "product_name": product_name,
                "stock_quantity": quantity,
                "reason": "no_inventory_group_match",
            })
            continue

        key = str(match.get("intent_key") or "")
        base_unit = str(match.get("default_base_unit") or "stuk")
        normalized_quantity, normalized_unit, quantity_source, confidence = infer_normalized_quantity(product_name, quantity, base_unit)
        group = grouped.setdefault(key, {
            "inventory_group_key": key,
            "display_name": str(match.get("display_name") or key),
            "base_unit": base_unit,
            "total_normalized_quantity": 0.0,
            "known_quantity_items": 0,
            "unknown_quantity_items": 0,
            "item_count": 0,
            "locations": [],
            "products": [],
            "confidence": 1.0,
        })
        group["item_count"] += 1
        if normalized_quantity is None:
            group["unknown_quantity_items"] += 1
        else:
            group["known_quantity_items"] += 1
            group["total_normalized_quantity"] += normalized_quantity
        group["confidence"] = min(float(group.get("confidence") or 1.0), confidence)

        location_parts = [str(row.get("location_name") or "").strip(), str(row.get("sublocation_name") or "").strip()]
        location = " / ".join(part for part in location_parts if part)
        if location and location not in group["locations"]:
            group["locations"].append(location)
        group["products"].append({
            "inventory_id": str(row.get("id") or ""),
            "product_name": product_name,
            "stock_quantity": quantity,
            "normalized_quantity": normalized_quantity,
            "normalized_unit": normalized_unit,
            "quantity_source": quantity_source,
            "location": location or None,
        })

    items = sorted(grouped.values(), key=lambda item: str(item.get("display_name") or "").lower())
    for item in items:
        item["total_normalized_quantity"] = round(float(item.get("total_normalized_quantity") or 0), 3)
        item["confidence"] = round(float(item.get("confidence") or 0), 3)

    return {
        "ok": True,
        "items": items,
        "unresolved_items": unresolved,
        "total_groups": len(items),
        "total_unresolved_items": len(unresolved),
        "source": "inventory_group_projection_v1",
        "mutates_inventory": False,
    }


def link_global_product_to_inventory_group(
    global_product_id: str,
    inventory_group_key: str,
    comparison_group_key: str | None = None,
    confidence: float = 1.0,
    source: str = "user",
    confirmed_by_user: bool = True,
) -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    normalized_product_id = str(global_product_id or "").strip()
    normalized_group_key = str(inventory_group_key or "").strip()
    if not normalized_product_id:
        return {"ok": False, "error": "global_product_id is verplicht"}
    if not normalized_group_key:
        return {"ok": False, "error": "inventory_group_key is verplicht"}

    timestamp = now_iso()
    with engine.begin() as conn:
        group = conn.execute(
            text("SELECT * FROM product_inventory_groups WHERE inventory_group_key = :key AND COALESCE(active, 1) = 1 LIMIT 1"),
            {"key": normalized_group_key},
        ).mappings().first()
        if not group:
            return {"ok": False, "error": "Voorraadgroep niet gevonden"}

        existing = conn.execute(
            text(
                """
                SELECT id FROM product_group_memberships
                WHERE global_product_id = :global_product_id
                  AND inventory_group_key = :inventory_group_key
                LIMIT 1
                """
            ),
            {"global_product_id": normalized_product_id, "inventory_group_key": normalized_group_key},
        ).mappings().first()

        membership_id = str(existing.get("id")) if existing else str(uuid.uuid4())
        params = {
            "id": membership_id,
            "global_product_id": normalized_product_id,
            "inventory_group_key": normalized_group_key,
            "comparison_group_key": str(comparison_group_key or normalized_group_key).strip(),
            "confidence": float(confidence or 1.0),
            "source": str(source or "user").strip(),
            "confirmed_by_user": 1 if confirmed_by_user else 0,
            "updated_at": timestamp,
            "created_at": timestamp,
        }
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE product_group_memberships
                    SET comparison_group_key = :comparison_group_key,
                        confidence = :confidence,
                        source = :source,
                        confirmed_by_user = :confirmed_by_user,
                        active = 1,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO product_group_memberships (id, global_product_id, inventory_group_key, comparison_group_key, confidence, source, confirmed_by_user, active, created_at, updated_at)
                    VALUES (:id, :global_product_id, :inventory_group_key, :comparison_group_key, :confidence, :source, :confirmed_by_user, 1, :created_at, :updated_at)
                    """
                ),
                params,
            )

    return {
        "ok": True,
        "membership_id": membership_id,
        "global_product_id": normalized_product_id,
        "inventory_group_key": normalized_group_key,
        "comparison_group_key": params["comparison_group_key"],
        "creates_inventory_event": False,
        "mutates_inventory": False,
    }
