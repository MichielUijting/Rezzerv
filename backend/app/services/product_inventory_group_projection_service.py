from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema, list_inventory_groups

GPC_COLUMNS: dict[str, str] = {
    "gpc_family_code": "TEXT",
    "gpc_family_name": "TEXT",
    "gpc_class_code": "TEXT",
    "gpc_class_name": "TEXT",
    "gpc_brick_code": "TEXT",
    "source": "TEXT",
}


def _get_columns(conn, table_name: str) -> set[str]:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}
    rows = conn.execute(
        text("""SELECT column_name FROM information_schema.columns WHERE table_name = :table_name"""),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def ensure_product_group_hierarchy_columns() -> None:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        columns = _get_columns(conn, "product_inventory_groups")
        for column_name, column_definition in GPC_COLUMNS.items():
            if column_name not in columns:
                conn.execute(text(f"ALTER TABLE product_inventory_groups ADD COLUMN {column_name} {column_definition}"))


def _hierarchy_options() -> list[dict[str, Any]]:
    ensure_product_group_hierarchy_columns()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                inventory_group_key,
                display_name,
                default_base_unit,
                gpc_family_code,
                gpc_family_name,
                gpc_class_code,
                gpc_class_name,
                gpc_brick_code,
                source
            FROM product_inventory_groups
            WHERE COALESCE(active, 1) = 1
            ORDER BY
                lower(COALESCE(gpc_family_name, '')) ASC,
                lower(COALESCE(gpc_class_name, '')) ASC,
                lower(display_name) ASC,
                inventory_group_key ASC
        """)).mappings().all()
    return [dict(row) for row in rows]


def _empty_hierarchy() -> dict[str, str]:
    return {
        "gpc_family_code": "",
        "gpc_family_name": "",
        "gpc_class_code": "",
        "gpc_class_name": "",
        "gpc_brick_code": "",
        "source": "",
    }


def list_inventory_groups_with_hierarchy(household_id: str | None = None) -> dict[str, Any]:
    payload = list_inventory_groups(household_id=household_id)
    group_options = _hierarchy_options()
    by_key = {str(group.get("inventory_group_key") or ""): group for group in group_options}

    for group in payload.get("items") or []:
        key = str(group.get("inventory_group_key") or "")
        hierarchy = by_key.get(key) or _empty_hierarchy()
        group.update({key: hierarchy.get(key) or "" for key in _empty_hierarchy()})
        group["hoofdgroep"] = group.get("gpc_family_name") or ""
        group["groep"] = group.get("gpc_class_name") or ""
        group["productgroep"] = group.get("display_name") or key
        for product in group.get("products") or []:
            product["gpc_family_name"] = group.get("gpc_family_name") or ""
            product["gpc_class_name"] = group.get("gpc_class_name") or ""
            product["gpc_brick_code"] = group.get("gpc_brick_code") or ""

    for item in payload.get("unresolved_items") or []:
        item.update(_empty_hierarchy())

    payload["group_options"] = group_options
    payload["source"] = "inventory_group_projection_v2_gpc_hierarchy"
    payload["mutates_inventory"] = False
    return payload
