from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema
from app.services.product_type_resolution_service import resolve_product_type
from app.services.product_type_unit_conversion_service import resolve_package_conversion


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _inventory_rows(household_id: str) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        inventory_columns = _columns(conn, "inventory")
        if not inventory_columns:
            return []
        quantity_column = "aantal" if "aantal" in inventory_columns else "quantity" if "quantity" in inventory_columns else None
        if not quantity_column:
            return []
        household_article_expr = "i.household_article_id" if "household_article_id" in inventory_columns else "NULL"
        global_product_expr = "i.global_product_id" if "global_product_id" in inventory_columns else "NULL"
        name_expr = "i.naam" if "naam" in inventory_columns else "i.name" if "name" in inventory_columns else "''"
        location_expr = "i.location_id" if "location_id" in inventory_columns else "i.sublocation_id" if "sublocation_id" in inventory_columns else "NULL"
        status_filter = "AND COALESCE(i.status, 'active') = 'active'" if "status" in inventory_columns else ""
        identity_join = ""
        identity_expr = "NULL"
        identity_columns = _columns(conn, "product_identities")
        if identity_columns and "household_article_id" in identity_columns and "global_product_id" in identity_columns:
            identity_join = f"""
                LEFT JOIN product_identities pi
                  ON pi.household_article_id = {household_article_expr}
                 AND COALESCE(pi.is_primary, 1) = 1
            """
            identity_expr = "pi.global_product_id"
        rows = conn.execute(
            text(
                f"""
                SELECT i.id AS inventory_id,
                       i.{quantity_column} AS package_count,
                       {name_expr} AS inventory_name,
                       {household_article_expr} AS household_article_id,
                       {global_product_expr} AS inventory_global_product_id,
                       {identity_expr} AS identity_global_product_id,
                       {location_expr} AS location_id
                FROM inventory i
                {identity_join}
                WHERE i.household_id = :household_id
                  {status_filter}
                ORDER BY i.id
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
        return [dict(row) for row in rows]


def build_product_type_inventory_projection(household_id: str) -> dict[str, Any]:
    """Projecteer artikelvoorraad read-only naar één regel per GPC Producttype."""
    ensure_product_inventory_group_schema()
    household_id = _clean(household_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")

    aggregates: dict[str, dict[str, Any]] = {}
    exceptions: list[dict[str, Any]] = []
    source_rows = _inventory_rows(household_id)

    for row in source_rows:
        household_article_id = _clean(row.get("household_article_id"))
        global_product_id = _clean(row.get("inventory_global_product_id") or row.get("identity_global_product_id"))
        inventory_id = _clean(row.get("inventory_id"))
        resolution = resolve_product_type(
            household_article_id=household_article_id or None,
            global_product_id=global_product_id or None,
            inventory_id=inventory_id or None,
        )
        if resolution.get("status") != "resolved":
            exceptions.append({
                "inventory_id": inventory_id or None,
                "household_article_id": household_article_id or None,
                "global_product_id": global_product_id or None,
                "inventory_name": row.get("inventory_name"),
                "status": resolution.get("status"),
            })
            continue

        product_type = dict(resolution.get("product_type") or {})
        product_type_id = _clean(product_type.get("product_type_id"))
        base_unit = _clean(product_type.get("base_unit")) or "stuk"
        package_count = _number(row.get("package_count"))
        if package_count is None or package_count < 0:
            exceptions.append({
                "inventory_id": inventory_id or None,
                "household_article_id": household_article_id or None,
                "global_product_id": global_product_id or None,
                "product_type_id": product_type_id or None,
                "inventory_name": row.get("inventory_name"),
                "status": "invalid_quantity",
            })
            continue

        conversion = resolve_package_conversion(
            global_product_id=global_product_id or None,
            product_type_id=product_type_id,
            target_unit=base_unit,
            allow_direct_count=True,
        )
        quantity_per_package = _number(conversion.get("quantity_per_package"))
        if quantity_per_package is None:
            exceptions.append({
                "inventory_id": inventory_id or None,
                "household_article_id": household_article_id or None,
                "global_product_id": global_product_id or None,
                "product_type_id": product_type_id or None,
                "inventory_name": row.get("inventory_name"),
                "status": conversion.get("status"),
            })
            continue

        target = aggregates.setdefault(product_type_id, {
            "product_type_id": product_type_id,
            "product_type_name": product_type.get("product_type_name") or product_type_id,
            "base_unit": base_unit,
            "aggregation_mode": product_type.get("aggregation_mode") or "sum_quantity",
            "current_quantity": 0.0,
            "contributing_inventory_rows": 0,
            "contributing_article_ids": set(),
            "contributing_location_ids": set(),
            "source_rows": [],
        })
        converted_quantity = package_count * quantity_per_package
        target["current_quantity"] += converted_quantity
        target["contributing_inventory_rows"] += 1
        if household_article_id:
            target["contributing_article_ids"].add(household_article_id)
        location_id = _clean(row.get("location_id"))
        if location_id:
            target["contributing_location_ids"].add(location_id)
        target["source_rows"].append({
            "inventory_id": inventory_id,
            "household_article_id": household_article_id or None,
            "global_product_id": global_product_id or None,
            "package_count": package_count,
            "quantity_per_package": quantity_per_package,
            "converted_quantity": converted_quantity,
            "base_unit": base_unit,
            "conversion_status": conversion.get("status"),
        })

    items: list[dict[str, Any]] = []
    for target in aggregates.values():
        items.append({
            "product_type_id": target["product_type_id"],
            "product_type_name": target["product_type_name"],
            "base_unit": target["base_unit"],
            "aggregation_mode": target["aggregation_mode"],
            "current_quantity": target["current_quantity"],
            "contributing_inventory_rows": target["contributing_inventory_rows"],
            "contributing_articles": len(target["contributing_article_ids"]),
            "contributing_locations": len(target["contributing_location_ids"]),
            "source_rows": target["source_rows"],
        })
    items.sort(key=lambda item: (str(item.get("product_type_name") or "").lower(), str(item.get("product_type_id") or "")))

    return {
        "household_id": household_id,
        "basis": "product_type",
        "read_only": True,
        "mutates_inventory": False,
        "source_inventory_rows": len(source_rows),
        "projected_inventory_rows": sum(int(item["contributing_inventory_rows"]) for item in items),
        "excluded_inventory_rows": len(exceptions),
        "product_types": len(items),
        "items": items,
        "exceptions": exceptions,
        "all_inventory_projected": len(exceptions) == 0,
    }
