from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_type_almost_out_service import (
    ensure_household_product_type_settings_schema,
)

EXTENDED_COLUMNS: dict[str, str] = {
    "favorite_store": "TEXT",
    "average_price": "REAL",
    "status": "TEXT DEFAULT 'active'",
    "default_location_id": "TEXT",
    "default_sublocation_id": "TEXT",
    "auto_restock": "INTEGER DEFAULT 0",
    "packaging_unit": "TEXT",
    "packaging_quantity": "REAL",
    "notes": "TEXT",
}

MIGRATABLE_FIELDS = (
    "min_stock",
    "ideal_stock",
    "favorite_store",
    "average_price",
    "status",
    "default_location_id",
    "default_sublocation_id",
    "auto_restock",
    "packaging_unit",
    "packaging_quantity",
    "notes",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Numerieke instelling bevat een ongeldige waarde")
    return number


def _columns(conn, table_name: str) -> set[str]:
    if str(engine.dialect.name or "").lower() == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table_name"),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def ensure_extended_product_type_settings_schema() -> None:
    ensure_household_product_type_settings_schema()
    with engine.begin() as conn:
        existing = _columns(conn, "household_product_type_settings")
        for name, definition in EXTENDED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE household_product_type_settings ADD COLUMN {name} {definition}"))


def _validate_household_location(conn, household_id: str, location_id: str | None, sublocation_id: str | None) -> None:
    location_id = _clean(location_id)
    sublocation_id = _clean(sublocation_id)
    if sublocation_id and not location_id:
        raise ValueError("Een standaardsublocatie vereist een standaardruimte")
    if location_id:
        row = conn.execute(
            text("SELECT id FROM spaces WHERE id = :id AND household_id = :household_id AND COALESCE(active, 1) = 1 LIMIT 1"),
            {"id": location_id, "household_id": household_id},
        ).mappings().first()
        if not row:
            raise ValueError("Standaardruimte hoort niet bij dit huishouden of is niet actief")
    if sublocation_id:
        row = conn.execute(
            text(
                "SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id "
                "WHERE sl.id = :id AND sl.space_id = :space_id AND s.household_id = :household_id "
                "AND COALESCE(sl.active, 1) = 1 LIMIT 1"
            ),
            {"id": sublocation_id, "space_id": location_id, "household_id": household_id},
        ).mappings().first()
        if not row:
            raise ValueError("Standaardsublocatie hoort niet bij de gekozen standaardruimte")


def list_extended_product_type_settings(household_id: str) -> dict[str, Any]:
    ensure_extended_product_type_settings_schema()
    household_id = _clean(household_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.*, g.display_name AS product_type_name,
                       g.default_base_unit AS base_unit,
                       g.aggregation_mode
                FROM household_product_type_settings s
                JOIN product_inventory_groups g ON g.inventory_group_key = s.product_type_id
                WHERE s.household_id = :household_id
                ORDER BY lower(g.display_name), s.product_type_id
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
    return {"household_id": household_id, "basis": "product_type", "items": [dict(row) for row in rows]}


def upsert_extended_product_type_setting(*, household_id: str, product_type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_extended_product_type_settings_schema()
    household_id = _clean(household_id)
    product_type_id = _clean(product_type_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    if not product_type_id:
        raise ValueError("Producttype ontbreekt")

    min_stock = _number(payload.get("min_stock"))
    ideal_stock = _number(payload.get("ideal_stock"))
    average_price = _number(payload.get("average_price"))
    packaging_quantity = _number(payload.get("packaging_quantity"))
    for label, value in (
        ("Minimumvoorraad", min_stock),
        ("Streefvoorraad", ideal_stock),
        ("Prijsindicatie", average_price),
        ("Verpakkingshoeveelheid", packaging_quantity),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{label} mag niet negatief zijn")
    if min_stock is not None and ideal_stock is not None and ideal_stock < min_stock:
        raise ValueError("Streefvoorraad moet gelijk aan of hoger dan minimumvoorraad zijn")

    status = _clean(payload.get("status") or ("active" if payload.get("active", True) else "inactive")).lower()
    if status not in {"active", "inactive"}:
        raise ValueError("Status moet active of inactive zijn")
    packaging_unit = _clean(payload.get("packaging_unit"))
    if packaging_quantity is not None and packaging_quantity > 0 and not packaging_unit:
        raise ValueError("Verpakkingseenheid ontbreekt bij de verpakkingshoeveelheid")

    params = {
        "household_id": household_id,
        "product_type_id": product_type_id,
        "min_stock": min_stock,
        "ideal_stock": ideal_stock,
        "consumable": 1 if bool(payload.get("consumable", True)) else 0,
        "active": 1 if status == "active" else 0,
        "favorite_store": _clean(payload.get("favorite_store")),
        "average_price": average_price,
        "status": status,
        "default_location_id": _clean(payload.get("default_location_id")) or None,
        "default_sublocation_id": _clean(payload.get("default_sublocation_id")) or None,
        "auto_restock": 1 if bool(payload.get("auto_restock", False)) else 0,
        "packaging_unit": packaging_unit,
        "packaging_quantity": packaging_quantity,
        "notes": _clean(payload.get("notes")),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    with engine.begin() as conn:
        group = conn.execute(
            text(
                "SELECT inventory_group_key FROM product_inventory_groups "
                "WHERE inventory_group_key = :id AND COALESCE(active, 1) = 1 "
                "AND inventory_group_key LIKE 'gpc:%' AND source LIKE 'gs1_gpc_%' LIMIT 1"
            ),
            {"id": product_type_id},
        ).mappings().first()
        if not group:
            raise ValueError("Bijna op gebruikt uitsluitend actieve officiële GS1 GPC Producttypen")
        _validate_household_location(conn, household_id, params["default_location_id"], params["default_sublocation_id"])
        conn.execute(
            text(
                """
                INSERT INTO household_product_type_settings (
                    household_id, product_type_id, min_stock, ideal_stock, consumable, active,
                    favorite_store, average_price, status, default_location_id, default_sublocation_id,
                    auto_restock, packaging_unit, packaging_quantity, notes, created_at, updated_at
                ) VALUES (
                    :household_id, :product_type_id, :min_stock, :ideal_stock, :consumable, :active,
                    :favorite_store, :average_price, :status, :default_location_id, :default_sublocation_id,
                    :auto_restock, :packaging_unit, :packaging_quantity, :notes, :created_at, :updated_at
                )
                ON CONFLICT(household_id, product_type_id) DO UPDATE SET
                    min_stock = excluded.min_stock,
                    ideal_stock = excluded.ideal_stock,
                    consumable = excluded.consumable,
                    active = excluded.active,
                    favorite_store = excluded.favorite_store,
                    average_price = excluded.average_price,
                    status = excluded.status,
                    default_location_id = excluded.default_location_id,
                    default_sublocation_id = excluded.default_sublocation_id,
                    auto_restock = excluded.auto_restock,
                    packaging_unit = excluded.packaging_unit,
                    packaging_quantity = excluded.packaging_quantity,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """
            ),
            params,
        )
        saved = conn.execute(
            text("SELECT * FROM household_product_type_settings WHERE household_id = :household_id AND product_type_id = :product_type_id LIMIT 1"),
            params,
        ).mappings().first()
    return {"ok": True, "basis": "product_type", "setting": dict(saved or {})}


def _value_key(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{float(value):.12g}"
    return _clean(value).lower()


def _resolve_field(source_rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for row in source_rows:
        value = row.get(field)
        key = _value_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        values.append(value)
    if not values:
        return {"status": "missing", "proposed_value": None, "values": []}
    if len(values) == 1:
        return {"status": "ready", "proposed_value": values[0], "values": values}
    return {"status": "conflict", "proposed_value": None, "values": values}


def analyze_household_article_settings_migration(household_id: str) -> dict[str, Any]:
    """Read-only analyse: groepeer bestaande huishoudartikelinstellingen per bevestigd Producttype."""
    ensure_extended_product_type_settings_schema()
    household_id = _clean(household_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")

    with engine.begin() as conn:
        article_columns = _columns(conn, "household_articles")
        settings_columns = _columns(conn, "household_article_settings")
        identity_columns = _columns(conn, "product_identities")
        if not article_columns or not settings_columns or not identity_columns:
            return {"household_id": household_id, "read_only": True, "items": [], "unmapped_articles": [], "reason": "source_schema_incomplete"}

        article_name_expr = "ha.naam" if "naam" in article_columns else "ha.name" if "name" in article_columns else "ha.id"
        select_settings = []
        for field in MIGRATABLE_FIELDS:
            select_settings.append(f"has.{field} AS {field}" if field in settings_columns else f"NULL AS {field}")
        settings_join_key = "household_article_id" if "household_article_id" in settings_columns else "article_id" if "article_id" in settings_columns else None
        identity_article_key = "household_article_id" if "household_article_id" in identity_columns else "article_id" if "article_id" in identity_columns else None
        if not settings_join_key or not identity_article_key:
            return {"household_id": household_id, "read_only": True, "items": [], "unmapped_articles": [], "reason": "source_keys_incomplete"}

        rows = conn.execute(
            text(
                f"""
                SELECT ha.id AS household_article_id,
                       {article_name_expr} AS household_article_name,
                       pi.global_product_id,
                       pgm.inventory_group_key AS product_type_id,
                       pig.display_name AS product_type_name,
                       pig.default_base_unit AS base_unit,
                       {', '.join(select_settings)}
                FROM household_articles ha
                LEFT JOIN household_article_settings has ON has.{settings_join_key} = ha.id
                LEFT JOIN product_identities pi ON pi.{identity_article_key} = ha.id AND COALESCE(pi.is_primary, 1) = 1
                LEFT JOIN product_group_memberships pgm ON pgm.global_product_id = pi.global_product_id AND COALESCE(pgm.active, 1) = 1
                LEFT JOIN product_inventory_groups pig ON pig.inventory_group_key = pgm.inventory_group_key AND COALESCE(pig.active, 1) = 1
                WHERE ha.household_id = :household_id
                  AND COALESCE(ha.status, 'active') = 'active'
                ORDER BY lower({article_name_expr}), ha.id
                """
            ),
            {"household_id": household_id},
        ).mappings().all()

    grouped: dict[str, dict[str, Any]] = {}
    unmapped: list[dict[str, Any]] = []
    unmapped_article_ids: set[str] = set()
    for raw in rows:
        row = dict(raw)
        product_type_id = _clean(row.get("product_type_id"))
        source = {
            "household_article_id": row.get("household_article_id"),
            "household_article_name": row.get("household_article_name"),
            "global_product_id": row.get("global_product_id"),
            **{field: row.get(field) for field in MIGRATABLE_FIELDS},
        }
        source_article_id = _clean(source.get("household_article_id"))
        if not product_type_id:
            if not source_article_id or source_article_id not in unmapped_article_ids:
                unmapped.append(source)
                if source_article_id:
                    unmapped_article_ids.add(source_article_id)
            continue
        bucket = grouped.setdefault(product_type_id, {
            "product_type_id": product_type_id,
            "product_type_name": row.get("product_type_name"),
            "base_unit": row.get("base_unit"),
            "source_articles": [],
        })
        already_present = any(
            _clean(existing.get("household_article_id")) == source_article_id
            for existing in bucket["source_articles"]
        ) if source_article_id else False
        if not already_present:
            bucket["source_articles"].append(source)

    items: list[dict[str, Any]] = []
    for bucket in grouped.values():
        resolutions = {field: _resolve_field(bucket["source_articles"], field) for field in MIGRATABLE_FIELDS}
        conflict_fields = [field for field, result in resolutions.items() if result["status"] == "conflict"]
        ready_fields = [field for field, result in resolutions.items() if result["status"] == "ready"]
        proposed = {field: result["proposed_value"] for field, result in resolutions.items() if result["status"] == "ready"}
        status = "conflict" if conflict_fields else "ready" if ready_fields else "missing"
        quantity_review_required = bool(
            proposed.get("min_stock") is not None or proposed.get("ideal_stock") is not None
        ) and not bool(proposed.get("packaging_unit") and proposed.get("packaging_quantity"))
        items.append({
            **bucket,
            "migration_status": "review_required" if quantity_review_required and status == "ready" else status,
            "proposed_settings": proposed,
            "field_resolutions": resolutions,
            "conflict_fields": conflict_fields,
            "quantity_review_required": quantity_review_required,
        })

    items.sort(key=lambda item: (_clean(item.get("product_type_name")).lower(), item["product_type_id"]))
    return {
        "household_id": household_id,
        "basis": "product_type",
        "read_only": True,
        "items": items,
        "unmapped_articles": unmapped,
        "summary": {
            "product_types": len(items),
            "ready": sum(1 for item in items if item["migration_status"] == "ready"),
            "review_required": sum(1 for item in items if item["migration_status"] == "review_required"),
            "conflict": sum(1 for item in items if item["migration_status"] == "conflict"),
            "missing": sum(1 for item in items if item["migration_status"] == "missing"),
            "unmapped_articles": len(unmapped),
        },
    }
