from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine


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
    "product_taxonomy_terms": {
        "id",
        "intent_key",
        "term",
        "term_type",
        "language",
        "confidence",
        "source",
        "active",
        "created_at",
        "updated_at",
    },
    "product_inventory_groups": {
        "inventory_group_key",
        "display_name",
        "default_base_unit",
        "aggregation_mode",
        "active",
        "created_at",
        "updated_at",
        "source",
    },
    "product_group_memberships": {
        "id",
        "global_product_id",
        "inventory_group_key",
        "comparison_group_key",
        "confidence",
        "source",
        "confirmed_by_user",
        "active",
        "created_at",
        "updated_at",
    },
    "product_unit_conversions": {
        "id",
        "global_product_id",
        "inventory_group_key",
        "content_value",
        "content_unit",
        "base_quantity",
        "base_unit",
        "confidence",
        "source",
        "created_at",
        "updated_at",
    },
    "inventory_item_group_assignments": {
        "inventory_id",
        "inventory_group_key",
        "source",
        "confirmed_by_user",
        "active",
        "created_at",
        "updated_at",
    },
}

_REQUIRED_INDEXES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ux_product_taxonomy_intent_key": ("product_taxonomy", ("intent_key",), True),
    "idx_product_taxonomy_terms_intent": (
        "product_taxonomy_terms",
        ("intent_key", "active"),
        False,
    ),
    "idx_product_group_memberships_product": (
        "product_group_memberships",
        ("global_product_id", "inventory_group_key"),
        False,
    ),
    "idx_product_group_memberships_one_active_product_type": (
        "product_group_memberships",
        ("global_product_id",),
        True,
    ),
    "idx_inventory_item_group_assignments_group": (
        "inventory_item_group_assignments",
        ("inventory_group_key", "active"),
        False,
    ),
}

DEFAULT_TAXONOMY = [
    {"intent_key": "groente.courgette", "canonical_name": "Courgette", "category": "Groente", "product_type": "Verse groente", "default_base_unit": "kg", "terms": ["courgette", "zucchini"]},
    {"intent_key": "drank.wijn.rood", "canonical_name": "Rode wijn", "category": "Drank", "product_type": "Wijn", "default_base_unit": "l", "terms": ["rode wijn", "red wine", "rouge", "vino rosso"]},
    {"intent_key": "zuivel.melk.halfvol", "canonical_name": "Halfvolle melk", "category": "Zuivel", "product_type": "Melk", "default_base_unit": "l", "terms": ["halfvolle melk", "halfvol melk", "melk halfvol"]},
    {"intent_key": "saus.mosterd", "canonical_name": "Mosterd", "category": "Saus", "product_type": "Mosterd", "default_base_unit": "kg", "terms": ["mosterd", "mustard"]},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("ë", "e").replace("é", "e").replace("è", "e").replace("ï", "i")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _get_columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return set()
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns(table_name)
    }


def _validate_product_inventory_group_schema(conn) -> None:
    inspector = inspect(conn)
    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"Canonical inventory-group schema ontbreekt: tabel {table_name}. "
                "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
            )
        actual_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing = required_columns - actual_columns
        if missing:
            raise RuntimeError(
                f"Canonical inventory-group schema wijkt af: {table_name} mist "
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
                f"Canonical inventory-group index wijkt af: {index_name}; "
                f"expected={expected_columns!r}/{expected_unique}, "
                f"actual={actual_columns!r}/{bool((index or {}).get('unique'))}."
            )


def ensure_product_inventory_group_schema() -> None:
    """Validate Alembic-owned schema, then seed canonical reference data using DML only."""
    with engine.connect() as conn:
        _validate_product_inventory_group_schema(conn)
    with engine.begin() as conn:
        seed_default_inventory_groups(conn)


def _row_exists(conn, sql: str, params: dict[str, Any]) -> bool:
    return conn.execute(text(sql), params).mappings().first() is not None


def seed_default_inventory_groups(conn) -> None:
    timestamp = now_iso()
    for item in DEFAULT_TAXONOMY:
        intent_key = item["intent_key"]
        if not _row_exists(conn, "SELECT 1 FROM product_taxonomy WHERE intent_key = :intent_key LIMIT 1", {"intent_key": intent_key}):
            conn.execute(
                text("""
                    INSERT INTO product_taxonomy (
                        intent_key, canonical_name, category, product_type,
                        default_base_unit, is_active, created_at, updated_at
                    ) VALUES (
                        :intent_key, :canonical_name, :category, :product_type,
                        :default_base_unit, 1, :created_at, :updated_at
                    )
                """),
                {"created_at": timestamp, "updated_at": timestamp, **{key: item[key] for key in ["intent_key", "canonical_name", "category", "product_type", "default_base_unit"]}},
            )
        else:
            conn.execute(
                text("""
                    UPDATE product_taxonomy
                    SET canonical_name = COALESCE(NULLIF(canonical_name, ''), :canonical_name),
                        category = COALESCE(NULLIF(category, ''), :category),
                        product_type = COALESCE(NULLIF(product_type, ''), :product_type),
                        default_base_unit = COALESCE(NULLIF(default_base_unit, ''), :default_base_unit),
                        is_active = COALESCE(is_active, 1),
                        updated_at = :updated_at
                    WHERE intent_key = :intent_key
                """),
                {"updated_at": timestamp, **{key: item[key] for key in ["intent_key", "canonical_name", "category", "product_type", "default_base_unit"]}},
            )

        if not _row_exists(conn, "SELECT 1 FROM product_inventory_groups WHERE inventory_group_key = :key LIMIT 1", {"key": intent_key}):
            conn.execute(
                text("""
                    INSERT INTO product_inventory_groups (inventory_group_key, display_name, default_base_unit, aggregation_mode, active, created_at, updated_at)
                    VALUES (:inventory_group_key, :display_name, :default_base_unit, 'sum_quantity', 1, :created_at, :updated_at)
                """),
                {"inventory_group_key": intent_key, "display_name": item["canonical_name"], "default_base_unit": item["default_base_unit"], "created_at": timestamp, "updated_at": timestamp},
            )
        else:
            conn.execute(
                text("""
                    UPDATE product_inventory_groups
                    SET display_name = COALESCE(NULLIF(display_name, ''), :display_name),
                        default_base_unit = COALESCE(NULLIF(default_base_unit, ''), :default_base_unit),
                        aggregation_mode = COALESCE(NULLIF(aggregation_mode, ''), 'sum_quantity'),
                        active = COALESCE(active, 1),
                        updated_at = :updated_at
                    WHERE inventory_group_key = :inventory_group_key
                """),
                {"inventory_group_key": intent_key, "display_name": item["canonical_name"], "default_base_unit": item["default_base_unit"], "updated_at": timestamp},
            )

        for term_value in item["terms"]:
            normalized_term = normalize_text(term_value)
            if not _row_exists(conn, "SELECT 1 FROM product_taxonomy_terms WHERE intent_key = :intent_key AND lower(term) = lower(:term) LIMIT 1", {"intent_key": intent_key, "term": normalized_term}):
                conn.execute(
                    text("""
                        INSERT INTO product_taxonomy_terms (id, intent_key, term, term_type, language, confidence, source, active, created_at, updated_at)
                        VALUES (:id, :intent_key, :term, 'seed', 'nl', 1.0, 'm2c2i30a_seed', 1, :created_at, :updated_at)
                    """),
                    {"id": str(uuid.uuid4()), "intent_key": intent_key, "term": normalized_term, "created_at": timestamp, "updated_at": timestamp},
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
        text(f"""
            SELECT {', '.join(select_columns)}
            FROM inventory i
            {join_space}
            {join_sublocation}
            WHERE {' AND '.join(where_parts)}
            ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC
        """),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _taxonomy_terms(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT t.intent_key, t.term, COALESCE(t.confidence, 1.0) AS term_confidence, g.display_name, g.default_base_unit
        FROM product_taxonomy_terms t
        JOIN product_inventory_groups g ON g.inventory_group_key = t.intent_key
        WHERE COALESCE(t.active, 1) = 1 AND COALESCE(g.active, 1) = 1
        ORDER BY length(t.term) DESC, t.term ASC
    """)).mappings().all()
    return [dict(row) for row in rows]


def _inventory_group_options(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT inventory_group_key, display_name, default_base_unit
        FROM product_inventory_groups
        WHERE COALESCE(active, 1) = 1
        ORDER BY lower(display_name) ASC, inventory_group_key ASC
    """)).mappings().all()
    return [dict(row) for row in rows]


def _inventory_item_assignments(conn) -> dict[str, dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT a.inventory_id, a.inventory_group_key, g.display_name, g.default_base_unit
        FROM inventory_item_group_assignments a
        JOIN product_inventory_groups g ON g.inventory_group_key = a.inventory_group_key
        WHERE COALESCE(a.active, 1) = 1 AND COALESCE(g.active, 1) = 1
    """)).mappings().all()
    return {str(row.get("inventory_id") or ""): dict(row) for row in rows}


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


def _add_row_to_group(grouped: dict[str, dict[str, Any]], row: dict[str, Any], group_info: dict[str, Any], source: str) -> None:
    product_name = str(row.get("product_name") or "").strip()
    quantity = float(row.get("stock_quantity") or 0)
    key = str(group_info.get("intent_key") or group_info.get("inventory_group_key") or "")
    base_unit = str(group_info.get("default_base_unit") or "stuk")
    display_name = str(group_info.get("display_name") or key)
    normalized_quantity, normalized_unit, quantity_source, confidence = infer_normalized_quantity(product_name, quantity, base_unit)
    if source == "manual_assignment":
        confidence = max(confidence, 0.9)
    group = grouped.setdefault(key, {
        "inventory_group_key": key,
        "display_name": display_name,
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
        "classification_source": source,
    })


def list_inventory_groups(household_id: str | None = None) -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        terms = _taxonomy_terms(conn)
        inventory_rows = _inventory_rows(conn, household_id=household_id)
        group_options = _inventory_group_options(conn)
        assignments = _inventory_item_assignments(conn)

    grouped: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    for row in inventory_rows:
        inventory_id = str(row.get("id") or "")
        assignment = assignments.get(inventory_id)
        if assignment:
            _add_row_to_group(grouped, row, assignment, "manual_assignment")
            continue
        match = _match_inventory_group(str(row.get("product_name") or ""), terms)
        if match:
            _add_row_to_group(grouped, row, match, "taxonomy_match")
            continue
        unresolved.append({
            "inventory_id": inventory_id,
            "product_name": str(row.get("product_name") or "").strip(),
            "stock_quantity": float(row.get("stock_quantity") or 0),
            "reason": "no_inventory_group_match",
        })

    items = sorted(grouped.values(), key=lambda item: str(item.get("display_name") or "").lower())
    for item in items:
        item["total_normalized_quantity"] = round(float(item.get("total_normalized_quantity") or 0), 3)
        item["confidence"] = round(float(item.get("confidence") or 0), 3)

    return {
        "ok": True,
        "items": items,
        "unresolved_items": unresolved,
        "group_options": group_options,
        "total_groups": len(items),
        "total_unresolved_items": len(unresolved),
        "source": "inventory_group_projection_v1",
        "mutates_inventory": False,
    }


def assign_inventory_item_to_group(inventory_id: str, inventory_group_key: str, source: str = "user") -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    normalized_inventory_id = str(inventory_id or "").strip()
    normalized_group_key = str(inventory_group_key or "").strip()
    if not normalized_inventory_id:
        return {"ok": False, "error": "inventory_id is verplicht"}
    if not normalized_group_key:
        return {"ok": False, "error": "inventory_group_key is verplicht"}
    timestamp = now_iso()
    with engine.begin() as conn:
        inventory = conn.execute(text("SELECT id FROM inventory WHERE id = :id LIMIT 1"), {"id": normalized_inventory_id}).mappings().first()
        if not inventory:
            return {"ok": False, "error": "Voorraadartikel niet gevonden"}
        group = conn.execute(text("SELECT inventory_group_key FROM product_inventory_groups WHERE inventory_group_key = :key AND COALESCE(active, 1) = 1 LIMIT 1"), {"key": normalized_group_key}).mappings().first()
        if not group:
            return {"ok": False, "error": "Productgroep niet gevonden"}
        existing = conn.execute(text("SELECT inventory_id FROM inventory_item_group_assignments WHERE inventory_id = :inventory_id LIMIT 1"), {"inventory_id": normalized_inventory_id}).mappings().first()
        params = {"inventory_id": normalized_inventory_id, "inventory_group_key": normalized_group_key, "source": str(source or "user").strip() or "user", "created_at": timestamp, "updated_at": timestamp}
        if existing:
            conn.execute(text("""
                UPDATE inventory_item_group_assignments
                SET inventory_group_key = :inventory_group_key, source = :source, confirmed_by_user = 1, active = 1, updated_at = :updated_at
                WHERE inventory_id = :inventory_id
            """), params)
        else:
            conn.execute(text("""
                INSERT INTO inventory_item_group_assignments (inventory_id, inventory_group_key, source, confirmed_by_user, active, created_at, updated_at)
                VALUES (:inventory_id, :inventory_group_key, :source, 1, 1, :created_at, :updated_at)
            """), params)
    return {"ok": True, "inventory_id": normalized_inventory_id, "inventory_group_key": normalized_group_key, "mutates_inventory": False, "creates_inventory_event": False}


def normalize_product_type_key(value: Any) -> str:
    return ".".join(normalize_text(value).split())


def create_or_get_product_type_with_connection(
    conn,
    *,
    inventory_group_key: str | None = None,
    display_name: str | None = None,
    default_base_unit: str = "stuk",
    aggregation_mode: str = "count",
    source: str = "user",
) -> dict[str, Any]:
    normalized_name = str(display_name or "").strip()
    normalized_key = str(inventory_group_key or "").strip()
    if not normalized_key and normalized_name:
        normalized_key = normalize_product_type_key(normalized_name)
    if not normalized_key:
        return {"ok": False, "error": "Producttype is verplicht"}

    existing = conn.execute(text("""
        SELECT * FROM product_inventory_groups
        WHERE inventory_group_key = :key
        LIMIT 1
    """), {"key": normalized_key}).mappings().first()
    if existing:
        if not bool(existing.get("active", 1)):
            conn.execute(text("""
                UPDATE product_inventory_groups
                SET active = 1, updated_at = :updated_at
                WHERE inventory_group_key = :key
            """), {"key": normalized_key, "updated_at": now_iso()})
        return {"ok": True, "created": False, "product_type": dict(existing)}

    if not normalized_name:
        return {"ok": False, "error": "Onbekend Producttype; display_name is verplicht voor aanmaak"}

    normalized_unit = str(default_base_unit or "stuk").strip().lower() or "stuk"
    normalized_mode = str(aggregation_mode or "count").strip().lower() or "count"
    if normalized_mode not in {"count", "volume", "weight", "sum_quantity"}:
        return {"ok": False, "error": "aggregation_mode moet count, volume, weight of sum_quantity zijn"}

    timestamp = now_iso()
    conn.execute(text("""
        INSERT INTO product_inventory_groups (
            inventory_group_key, display_name, default_base_unit,
            aggregation_mode, active, created_at, updated_at, source
        ) VALUES (
            :key, :display_name, :default_base_unit,
            :aggregation_mode, 1, :created_at, :updated_at, :source
        )
    """), {
        "key": normalized_key,
        "display_name": normalized_name,
        "default_base_unit": normalized_unit,
        "aggregation_mode": normalized_mode,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": str(source or "user").strip() or "user",
    })
    created = conn.execute(text("""
        SELECT * FROM product_inventory_groups
        WHERE inventory_group_key = :key
        LIMIT 1
    """), {"key": normalized_key}).mappings().first()
    return {"ok": True, "created": True, "product_type": dict(created or {})}


def link_global_product_to_inventory_group_with_connection(
    conn,
    *,
    global_product_id: str,
    inventory_group_key: str,
    comparison_group_key: str | None = None,
    confidence: float = 1.0,
    source: str = "user",
    confirmed_by_user: bool = True,
) -> dict[str, Any]:
    normalized_product_id = str(global_product_id or "").strip()
    normalized_group_key = str(inventory_group_key or "").strip()
    if not normalized_product_id:
        return {"ok": False, "error": "global_product_id is verplicht"}
    if not normalized_group_key:
        return {"ok": False, "error": "inventory_group_key is verplicht"}

    product = conn.execute(text("SELECT id FROM global_products WHERE id = :id LIMIT 1"), {"id": normalized_product_id}).mappings().first()
    if not product:
        return {"ok": False, "error": "Universeel artikel niet gevonden"}
    group = conn.execute(text("""
        SELECT * FROM product_inventory_groups
        WHERE inventory_group_key = :key AND COALESCE(active, 1) = 1
        LIMIT 1
    """), {"key": normalized_group_key}).mappings().first()
    if not group:
        return {"ok": False, "error": "Producttype niet gevonden"}

    timestamp = now_iso()
    conn.execute(text("""
        UPDATE product_group_memberships
        SET active = 0, updated_at = :updated_at
        WHERE global_product_id = :global_product_id
          AND COALESCE(active, 1) = 1
          AND inventory_group_key <> :inventory_group_key
    """), {
        "global_product_id": normalized_product_id,
        "inventory_group_key": normalized_group_key,
        "updated_at": timestamp,
    })

    existing = conn.execute(text("""
        SELECT id FROM product_group_memberships
        WHERE global_product_id = :global_product_id
          AND inventory_group_key = :inventory_group_key
        LIMIT 1
    """), {
        "global_product_id": normalized_product_id,
        "inventory_group_key": normalized_group_key,
    }).mappings().first()

    membership_id = str(existing.get("id")) if existing else str(uuid.uuid4())
    params = {
        "id": membership_id,
        "global_product_id": normalized_product_id,
        "inventory_group_key": normalized_group_key,
        "comparison_group_key": str(comparison_group_key or normalized_group_key).strip(),
        "confidence": max(0.0, min(float(confidence or 1.0), 1.0)),
        "source": str(source or "user").strip() or "user",
        "confirmed_by_user": 1 if confirmed_by_user else 0,
        "updated_at": timestamp,
        "created_at": timestamp,
    }
    if existing:
        conn.execute(text("""
            UPDATE product_group_memberships
            SET comparison_group_key = :comparison_group_key,
                confidence = :confidence,
                source = :source,
                confirmed_by_user = :confirmed_by_user,
                active = 1,
                updated_at = :updated_at
            WHERE id = :id
        """), params)
    else:
        conn.execute(text("""
            INSERT INTO product_group_memberships (
                id, global_product_id, inventory_group_key,
                comparison_group_key, confidence, source,
                confirmed_by_user, active, created_at, updated_at
            ) VALUES (
                :id, :global_product_id, :inventory_group_key,
                :comparison_group_key, :confidence, :source,
                :confirmed_by_user, 1, :created_at, :updated_at
            )
        """), params)

    return {
        "ok": True,
        "membership_id": membership_id,
        "global_product_id": normalized_product_id,
        "inventory_group_key": normalized_group_key,
        "comparison_group_key": params["comparison_group_key"],
        "confirmed_by_user": bool(confirmed_by_user),
        "creates_inventory_event": False,
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
    with engine.begin() as conn:
        return link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=inventory_group_key,
            comparison_group_key=comparison_group_key,
            confidence=confidence,
            source=source,
            confirmed_by_user=confirmed_by_user,
        )
