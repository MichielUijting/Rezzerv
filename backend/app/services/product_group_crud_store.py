from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema, now_iso, normalize_text


def _slugify_group_name(value: str) -> str:
    normalized = normalize_text(value)
    slug = ".".join(part for part in re.split(r"\s+", normalized) if part)
    return f"productgroep.{slug or 'nieuw'}"


def _unique_group_key(conn, display_name: str) -> str:
    base_key = _slugify_group_name(display_name)
    candidate = base_key
    suffix = 2
    while conn.execute(
        text("SELECT 1 FROM product_inventory_groups WHERE inventory_group_key = :key LIMIT 1"),
        {"key": candidate},
    ).mappings().first():
        candidate = f"{base_key}.{suffix}"
        suffix += 1
    return candidate


def list_product_groups(include_inactive: bool = False) -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    where_clause = "1 = 1" if include_inactive else "COALESCE(active, 1) = 1"
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT inventory_group_key, display_name, default_base_unit, aggregation_mode, COALESCE(active, 1) AS active
                FROM product_inventory_groups
                WHERE {where_clause}
                ORDER BY lower(display_name) ASC, inventory_group_key ASC
                """
            )
        ).mappings().all()
    return {"ok": True, "items": [dict(row) for row in rows], "mutates_inventory": False}


def create_product_group(display_name: str, default_base_unit: str = "stuk") -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    normalized_name = str(display_name or "").strip()
    normalized_unit = str(default_base_unit or "stuk").strip().lower() or "stuk"
    if not normalized_name:
        return {"ok": False, "error": "Productgroepnaam is verplicht"}
    timestamp = now_iso()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT inventory_group_key FROM product_inventory_groups WHERE lower(display_name) = lower(:display_name) LIMIT 1"),
            {"display_name": normalized_name},
        ).mappings().first()
        if existing:
            return {"ok": False, "error": "Productgroep bestaat al"}
        group_key = _unique_group_key(conn, normalized_name)
        conn.execute(
            text(
                """
                INSERT INTO product_inventory_groups (inventory_group_key, display_name, default_base_unit, aggregation_mode, active, created_at, updated_at)
                VALUES (:inventory_group_key, :display_name, :default_base_unit, 'sum_quantity', 1, :created_at, :updated_at)
                """
            ),
            {
                "inventory_group_key": group_key,
                "display_name": normalized_name,
                "default_base_unit": normalized_unit,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO product_taxonomy (id, intent_key, canonical_name, category, product_type, default_base_unit, active, created_at, updated_at)
                VALUES (:id, :intent_key, :canonical_name, 'Handmatig', 'Productgroep', :default_base_unit, 1, :created_at, :updated_at)
                """
            ),
            {
                "id": group_key,
                "intent_key": group_key,
                "canonical_name": normalized_name,
                "default_base_unit": normalized_unit,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO product_taxonomy_terms (id, intent_key, term, term_type, language, confidence, source, active, created_at, updated_at)
                VALUES (:id, :intent_key, :term, 'manual', 'nl', 1.0, 'productgroepen_ui', 1, :created_at, :updated_at)
                """
            ),
            {
                "id": f"{group_key}.term",
                "intent_key": group_key,
                "term": normalize_text(normalized_name),
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
    return {"ok": True, "inventory_group_key": group_key, "display_name": normalized_name, "default_base_unit": normalized_unit, "mutates_inventory": False}


def update_product_group(inventory_group_key: str, display_name: str, default_base_unit: str = "stuk") -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    normalized_key = str(inventory_group_key or "").strip()
    normalized_name = str(display_name or "").strip()
    normalized_unit = str(default_base_unit or "stuk").strip().lower() or "stuk"
    if not normalized_key:
        return {"ok": False, "error": "inventory_group_key is verplicht"}
    if not normalized_name:
        return {"ok": False, "error": "Productgroepnaam is verplicht"}
    timestamp = now_iso()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT inventory_group_key FROM product_inventory_groups WHERE inventory_group_key = :key AND COALESCE(active, 1) = 1 LIMIT 1"),
            {"key": normalized_key},
        ).mappings().first()
        if not existing:
            return {"ok": False, "error": "Productgroep niet gevonden"}
        duplicate = conn.execute(
            text(
                """
                SELECT inventory_group_key FROM product_inventory_groups
                WHERE lower(display_name) = lower(:display_name)
                  AND inventory_group_key <> :key
                  AND COALESCE(active, 1) = 1
                LIMIT 1
                """
            ),
            {"display_name": normalized_name, "key": normalized_key},
        ).mappings().first()
        if duplicate:
            return {"ok": False, "error": "Productgroepnaam bestaat al"}
        conn.execute(
            text(
                """
                UPDATE product_inventory_groups
                SET display_name = :display_name,
                    default_base_unit = :default_base_unit,
                    updated_at = :updated_at
                WHERE inventory_group_key = :key
                """
            ),
            {"display_name": normalized_name, "default_base_unit": normalized_unit, "updated_at": timestamp, "key": normalized_key},
        )
        conn.execute(
            text(
                """
                UPDATE product_taxonomy
                SET canonical_name = :display_name,
                    default_base_unit = :default_base_unit,
                    updated_at = :updated_at
                WHERE intent_key = :key
                """
            ),
            {"display_name": normalized_name, "default_base_unit": normalized_unit, "updated_at": timestamp, "key": normalized_key},
        )
    return {"ok": True, "inventory_group_key": normalized_key, "display_name": normalized_name, "default_base_unit": normalized_unit, "mutates_inventory": False}


def delete_product_group(inventory_group_key: str) -> dict[str, Any]:
    ensure_product_inventory_group_schema()
    normalized_key = str(inventory_group_key or "").strip()
    if not normalized_key:
        return {"ok": False, "error": "inventory_group_key is verplicht"}
    timestamp = now_iso()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT inventory_group_key FROM product_inventory_groups WHERE inventory_group_key = :key AND COALESCE(active, 1) = 1 LIMIT 1"),
            {"key": normalized_key},
        ).mappings().first()
        if not existing:
            return {"ok": False, "error": "Productgroep niet gevonden"}
        conn.execute(
            text("UPDATE product_inventory_groups SET active = 0, updated_at = :updated_at WHERE inventory_group_key = :key"),
            {"updated_at": timestamp, "key": normalized_key},
        )
        conn.execute(
            text("UPDATE product_taxonomy SET active = 0, updated_at = :updated_at WHERE intent_key = :key"),
            {"updated_at": timestamp, "key": normalized_key},
        )
        conn.execute(
            text("UPDATE product_taxonomy_terms SET active = 0, updated_at = :updated_at WHERE intent_key = :key"),
            {"updated_at": timestamp, "key": normalized_key},
        )
        conn.execute(
            text("UPDATE inventory_item_group_assignments SET active = 0, updated_at = :updated_at WHERE inventory_group_key = :key"),
            {"updated_at": timestamp, "key": normalized_key},
        )
    return {"ok": True, "inventory_group_key": normalized_key, "mutates_inventory": False}
