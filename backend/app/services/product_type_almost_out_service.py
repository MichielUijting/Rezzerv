from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema


SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS household_product_type_settings (
    household_id TEXT NOT NULL,
    product_type_id TEXT NOT NULL,
    min_stock REAL,
    ideal_stock REAL,
    consumable INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (household_id, product_type_id)
)
"""

SETTINGS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_household_product_type_settings_household_active
ON household_product_type_settings (household_id, active, product_type_id)
"""

MASS_FACTORS = {
    "mg": ("mg", 1.0),
    "g": ("mg", 1000.0),
    "kg": ("mg", 1_000_000.0),
}
VOLUME_FACTORS = {
    "ml": ("ml", 1.0),
    "cl": ("ml", 10.0),
    "dl": ("ml", 100.0),
    "l": ("ml", 1000.0),
    "liter": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
}
COUNT_UNITS = {"stuk", "stuks", "piece", "pieces", "rol", "rollen", "wasbeurt", "wasbeurten"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _columns(conn, table_name: str) -> set[str]:
    dialect = str(engine.dialect.name or "").lower()
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table_name"),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def ensure_household_product_type_settings_schema() -> None:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        conn.execute(text(SETTINGS_TABLE_SQL))
        conn.execute(text(SETTINGS_INDEX_SQL))


def _official_product_type(conn, product_type_id: str) -> dict[str, Any]:
    normalized = _clean(product_type_id)
    if not normalized:
        raise ValueError("Producttype ontbreekt")
    row = conn.execute(
        text(
            """
            SELECT inventory_group_key, display_name, default_base_unit,
                   aggregation_mode, source, active
            FROM product_inventory_groups
            WHERE inventory_group_key = :product_type_id
              AND COALESCE(active, 1) = 1
            LIMIT 1
            """
        ),
        {"product_type_id": normalized},
    ).mappings().first()
    if not row:
        raise ValueError("Producttype bestaat niet of is niet actief")
    if not normalized.startswith("gpc:") or not str(row.get("source") or "").startswith("gs1_gpc_"):
        raise ValueError("Bijna op gebruikt uitsluitend officiële GS1 GPC Producttypen")
    return dict(row)


def list_household_product_type_settings(household_id: str) -> dict[str, Any]:
    ensure_household_product_type_settings_schema()
    normalized_household_id = _clean(household_id)
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.household_id, s.product_type_id, s.min_stock, s.ideal_stock,
                       s.consumable, s.active, s.created_at, s.updated_at,
                       g.display_name AS product_type_name,
                       g.default_base_unit AS base_unit,
                       g.aggregation_mode
                FROM household_product_type_settings s
                JOIN product_inventory_groups g
                  ON g.inventory_group_key = s.product_type_id
                WHERE s.household_id = :household_id
                ORDER BY lower(g.display_name), s.product_type_id
                """
            ),
            {"household_id": normalized_household_id},
        ).mappings().all()
    return {"household_id": normalized_household_id, "items": [dict(row) for row in rows]}


def upsert_household_product_type_setting(
    *,
    household_id: str,
    product_type_id: str,
    min_stock: float | None,
    ideal_stock: float | None,
    consumable: bool = True,
    active: bool = True,
) -> dict[str, Any]:
    ensure_household_product_type_settings_schema()
    normalized_household_id = _clean(household_id)
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    normalized_min = _number(min_stock)
    normalized_ideal = _number(ideal_stock)
    if normalized_min is not None and normalized_min < 0:
        raise ValueError("Minimumvoorraad mag niet negatief zijn")
    if normalized_ideal is not None and normalized_ideal < 0:
        raise ValueError("Streefvoorraad mag niet negatief zijn")
    if normalized_min is not None and normalized_ideal is not None and normalized_ideal < normalized_min:
        raise ValueError("Streefvoorraad moet gelijk aan of hoger dan minimumvoorraad zijn")
    timestamp = _now_iso()
    with engine.begin() as conn:
        group = _official_product_type(conn, product_type_id)
        params = {
            "household_id": normalized_household_id,
            "product_type_id": str(group["inventory_group_key"]),
            "min_stock": normalized_min,
            "ideal_stock": normalized_ideal,
            "consumable": 1 if consumable else 0,
            "active": 1 if active else 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        dialect = str(engine.dialect.name or "").lower()
        if dialect == "sqlite":
            conn.execute(
                text(
                    """
                    INSERT INTO household_product_type_settings (
                        household_id, product_type_id, min_stock, ideal_stock,
                        consumable, active, created_at, updated_at
                    ) VALUES (
                        :household_id, :product_type_id, :min_stock, :ideal_stock,
                        :consumable, :active, :created_at, :updated_at
                    )
                    ON CONFLICT(household_id, product_type_id) DO UPDATE SET
                        min_stock = excluded.min_stock,
                        ideal_stock = excluded.ideal_stock,
                        consumable = excluded.consumable,
                        active = excluded.active,
                        updated_at = excluded.updated_at
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO household_product_type_settings (
                        household_id, product_type_id, min_stock, ideal_stock,
                        consumable, active, created_at, updated_at
                    ) VALUES (
                        :household_id, :product_type_id, :min_stock, :ideal_stock,
                        :consumable, :active, :created_at, :updated_at
                    )
                    ON CONFLICT (household_id, product_type_id) DO UPDATE SET
                        min_stock = EXCLUDED.min_stock,
                        ideal_stock = EXCLUDED.ideal_stock,
                        consumable = EXCLUDED.consumable,
                        active = EXCLUDED.active,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                params,
            )
        saved = conn.execute(
            text(
                """
                SELECT s.*, g.display_name AS product_type_name,
                       g.default_base_unit AS base_unit,
                       g.aggregation_mode
                FROM household_product_type_settings s
                JOIN product_inventory_groups g
                  ON g.inventory_group_key = s.product_type_id
                WHERE s.household_id = :household_id
                  AND s.product_type_id = :product_type_id
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
    return {"ok": True, "setting": dict(saved or {})}


def _canonical_quantity(value: float, unit: str) -> tuple[float, str] | None:
    normalized_unit = _clean(unit).lower()
    if normalized_unit in MASS_FACTORS:
        canonical, factor = MASS_FACTORS[normalized_unit]
        return value * factor, canonical
    if normalized_unit in VOLUME_FACTORS:
        canonical, factor = VOLUME_FACTORS[normalized_unit]
        return value * factor, canonical
    if normalized_unit in COUNT_UNITS:
        return value, "stuk"
    return None


def _convert_quantity(value: float, source_unit: str, target_unit: str) -> float | None:
    source = _canonical_quantity(value, source_unit)
    target = _canonical_quantity(1.0, target_unit)
    if not source or not target or source[1] != target[1] or target[0] == 0:
        return None
    return source[0] / target[0]


def _inventory_source_rows(conn, household_id: str) -> list[dict[str, Any]]:
    inventory_columns = _columns(conn, "inventory")
    if not inventory_columns:
        return []
    quantity_column = "aantal" if "aantal" in inventory_columns else "quantity" if "quantity" in inventory_columns else None
    if not quantity_column:
        return []
    name_column = "naam" if "naam" in inventory_columns else "name" if "name" in inventory_columns else None
    household_article_expr = "i.household_article_id" if "household_article_id" in inventory_columns else "NULL"
    global_product_expr = "i.global_product_id" if "global_product_id" in inventory_columns else "NULL"
    status_filter = "AND COALESCE(i.status, 'active') = 'active'" if "status" in inventory_columns else ""
    rows = conn.execute(
        text(
            f"""
            SELECT i.id AS inventory_id,
                   i.{quantity_column} AS package_count,
                   {('i.' + name_column) if name_column else "''"} AS inventory_name,
                   {household_article_expr} AS household_article_id,
                   {global_product_expr} AS inventory_global_product_id,
                   iga.inventory_group_key AS direct_product_type_id,
                   pi.global_product_id AS identity_global_product_id
            FROM inventory i
            LEFT JOIN inventory_item_group_assignments iga
              ON iga.inventory_id = i.id AND COALESCE(iga.active, 1) = 1
            LEFT JOIN product_identities pi
              ON pi.household_article_id = {household_article_expr}
             AND COALESCE(pi.is_primary, 1) = 1
            WHERE i.household_id = :household_id
              {status_filter}
            """
        ),
        {"household_id": household_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _membership(conn, global_product_id: str) -> dict[str, Any] | None:
    normalized = _clean(global_product_id)
    if not normalized:
        return None
    row = conn.execute(
        text(
            """
            SELECT pgm.inventory_group_key, pgm.global_product_id,
                   pig.display_name, pig.default_base_unit,
                   pig.aggregation_mode
            FROM product_group_memberships pgm
            JOIN product_inventory_groups pig
              ON pig.inventory_group_key = pgm.inventory_group_key
            WHERE pgm.global_product_id = :global_product_id
              AND COALESCE(pgm.active, 1) = 1
              AND COALESCE(pig.active, 1) = 1
            ORDER BY COALESCE(pgm.confirmed_by_user, 0) DESC,
                     COALESCE(pgm.updated_at, pgm.created_at, '') DESC
            LIMIT 1
            """
        ),
        {"global_product_id": normalized},
    ).mappings().first()
    return dict(row) if row else None


def _conversion(conn, global_product_id: str, product_type_id: str, target_unit: str) -> tuple[float | None, str]:
    normalized_product_id = _clean(global_product_id)
    if not normalized_product_id:
        return None, "missing_product_identity"
    row = conn.execute(
        text(
            """
            SELECT base_quantity, base_unit, content_value, content_unit
            FROM product_unit_conversions
            WHERE global_product_id = :global_product_id
              AND (inventory_group_key = :product_type_id OR inventory_group_key IS NULL OR trim(inventory_group_key) = '')
            ORDER BY CASE WHEN inventory_group_key = :product_type_id THEN 0 ELSE 1 END,
                     confidence DESC, COALESCE(updated_at, created_at, '') DESC
            LIMIT 1
            """
        ),
        {"global_product_id": normalized_product_id, "product_type_id": product_type_id},
    ).mappings().first()
    if not row:
        return None, "missing_unit_conversion"
    base_quantity = _number(row.get("base_quantity"))
    base_unit = _clean(row.get("base_unit"))
    if base_quantity is not None and base_quantity >= 0 and base_unit:
        converted = _convert_quantity(base_quantity, base_unit, target_unit)
        return converted, "ok" if converted is not None else "incompatible_unit"
    content_value = _number(row.get("content_value"))
    content_unit = _clean(row.get("content_unit"))
    if content_value is not None and content_value >= 0 and content_unit:
        converted = _convert_quantity(content_value, content_unit, target_unit)
        return converted, "ok" if converted is not None else "incompatible_unit"
    return None, "missing_unit_conversion"


def build_product_type_almost_out_preview(household_id: str) -> dict[str, Any]:
    ensure_household_product_type_settings_schema()
    normalized_household_id = _clean(household_id)
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    with engine.begin() as conn:
        settings = conn.execute(
            text(
                """
                SELECT s.*, g.display_name AS product_type_name,
                       g.default_base_unit AS base_unit,
                       g.aggregation_mode
                FROM household_product_type_settings s
                JOIN product_inventory_groups g
                  ON g.inventory_group_key = s.product_type_id
                WHERE s.household_id = :household_id
                  AND COALESCE(s.active, 1) = 1
                  AND COALESCE(s.consumable, 1) = 1
                  AND COALESCE(g.active, 1) = 1
                ORDER BY lower(g.display_name), s.product_type_id
                """
            ),
            {"household_id": normalized_household_id},
        ).mappings().all()
        aggregates: dict[str, dict[str, Any]] = {}
        for setting in settings:
            product_type_id = str(setting.get("product_type_id") or "")
            aggregates[product_type_id] = {
                "product_type_id": product_type_id,
                "product_type_name": str(setting.get("product_type_name") or product_type_id),
                "base_unit": str(setting.get("base_unit") or "stuk"),
                "aggregation_mode": str(setting.get("aggregation_mode") or "sum_quantity"),
                "current_quantity": 0.0,
                "min_stock": _number(setting.get("min_stock")),
                "ideal_stock": _number(setting.get("ideal_stock")),
                "contributing_articles": set(),
                "contributing_inventory_rows": 0,
                "excluded_inventory_rows": [],
            }
        for source in _inventory_source_rows(conn, normalized_household_id):
            global_product_id = _clean(source.get("inventory_global_product_id") or source.get("identity_global_product_id"))
            membership = _membership(conn, global_product_id)
            product_type_id = _clean(source.get("direct_product_type_id") or (membership or {}).get("inventory_group_key"))
            if product_type_id not in aggregates:
                continue
            target = aggregates[product_type_id]
            package_count = _number(source.get("package_count"))
            if package_count is None or package_count < 0:
                target["excluded_inventory_rows"].append({
                    "inventory_id": source.get("inventory_id"),
                    "reason": "invalid_quantity",
                })
                continue
            per_package, conversion_state = _conversion(conn, global_product_id, product_type_id, target["base_unit"])
            if per_package is None:
                canonical_target = _canonical_quantity(1.0, target["base_unit"])
                if product_type_id == _clean(source.get("direct_product_type_id")) and canonical_target and canonical_target[1] == "stuk":
                    per_package = 1.0
                    conversion_state = "direct_count"
                else:
                    target["excluded_inventory_rows"].append({
                        "inventory_id": source.get("inventory_id"),
                        "household_article_id": source.get("household_article_id"),
                        "global_product_id": global_product_id or None,
                        "reason": conversion_state,
                    })
                    continue
            target["current_quantity"] += package_count * per_package
            target["contributing_inventory_rows"] += 1
            if source.get("household_article_id"):
                target["contributing_articles"].add(str(source.get("household_article_id")))
        items: list[dict[str, Any]] = []
        for target in aggregates.values():
            current = float(target["current_quantity"])
            minimum = target["min_stock"]
            ideal = target["ideal_stock"]
            include = minimum is not None and current <= minimum
            amount_to_buy = max(0.0, float(ideal or 0.0) - current) if ideal is not None else 0.0
            excluded = list(target["excluded_inventory_rows"])
            if minimum is None:
                reason = "missing_minimum"
                data_state = "missing_setting"
            elif excluded:
                reason = "below_or_equal_minimum" if include else "above_minimum"
                data_state = "incomplete_quantity"
            else:
                reason = "below_or_equal_minimum" if include else "above_minimum"
                data_state = "ok"
            items.append({
                "product_type_id": target["product_type_id"],
                "product_type_name": target["product_type_name"],
                "base_unit": target["base_unit"],
                "aggregation_mode": target["aggregation_mode"],
                "current_quantity": current,
                "min_stock": minimum,
                "ideal_stock": ideal,
                "amount_to_buy": amount_to_buy,
                "include_in_almost_out": include,
                "reason": reason,
                "data_state": data_state,
                "contributing_articles": len(target["contributing_articles"]),
                "contributing_inventory_rows": target["contributing_inventory_rows"],
                "excluded_inventory_rows": excluded,
            })
    return {
        "household_id": normalized_household_id,
        "basis": "product_type",
        "read_only": True,
        "items": items,
        "almost_out_items": [item for item in items if item["include_in_almost_out"]],
    }
