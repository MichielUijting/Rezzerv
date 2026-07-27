from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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


def resolve_product_type(
    *,
    household_article_id: str | None = None,
    global_product_id: str | None = None,
    inventory_id: str | None = None,
) -> dict[str, Any]:
    """Resolveer via één centrale keten exact één actief GPC Producttype.

    De resolver muteert geen voorraad en geeft altijd een expliciete status terug.
    """
    ensure_product_inventory_group_schema()
    household_article_id = _clean(household_article_id)
    global_product_id = _clean(global_product_id)
    inventory_id = _clean(inventory_id)

    with engine.begin() as conn:
        direct_product_type_id = ""
        if inventory_id:
            assignment = conn.execute(
                text(
                    """
                    SELECT inventory_group_key
                    FROM inventory_item_group_assignments
                    WHERE inventory_id = :inventory_id
                      AND COALESCE(active, 1) = 1
                    LIMIT 1
                    """
                ),
                {"inventory_id": inventory_id},
            ).mappings().first()
            direct_product_type_id = _clean((assignment or {}).get("inventory_group_key"))

        if not global_product_id and household_article_id:
            identity_columns = _columns(conn, "product_identities")
            if identity_columns:
                identity = conn.execute(
                    text(
                        """
                        SELECT global_product_id
                        FROM product_identities
                        WHERE household_article_id = :household_article_id
                          AND COALESCE(is_primary, 1) = 1
                        ORDER BY COALESCE(updated_at, created_at, '') DESC
                        LIMIT 1
                        """
                    ),
                    {"household_article_id": household_article_id},
                ).mappings().first()
                global_product_id = _clean((identity or {}).get("global_product_id"))

        if direct_product_type_id:
            membership_rows = [{"inventory_group_key": direct_product_type_id, "source": "inventory_assignment"}]
        elif global_product_id:
            membership_rows = conn.execute(
                text(
                    """
                    SELECT inventory_group_key, source, confidence, confirmed_by_user
                    FROM product_group_memberships
                    WHERE global_product_id = :global_product_id
                      AND COALESCE(active, 1) = 1
                    ORDER BY COALESCE(confirmed_by_user, 0) DESC,
                             COALESCE(updated_at, created_at, '') DESC
                    """
                ),
                {"global_product_id": global_product_id},
            ).mappings().all()
        else:
            membership_rows = []

        base = {
            "household_article_id": household_article_id or None,
            "global_product_id": global_product_id or None,
            "inventory_id": inventory_id or None,
            "read_only": True,
            "mutates_inventory": False,
        }

        if not household_article_id and not global_product_id and not inventory_id:
            return {**base, "status": "missing_household_article", "product_type": None}
        if not global_product_id and not direct_product_type_id:
            return {**base, "status": "missing_global_product", "product_type": None}
        if not membership_rows:
            return {**base, "status": "missing_product_type", "product_type": None}
        if len(membership_rows) > 1:
            return {
                **base,
                "status": "ambiguous_product_type",
                "product_type": None,
                "candidate_product_type_ids": [str(row.get("inventory_group_key") or "") for row in membership_rows],
            }

        product_type_id = _clean(membership_rows[0].get("inventory_group_key"))
        group = conn.execute(
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
            {"product_type_id": product_type_id},
        ).mappings().first()
        if not group or not product_type_id.startswith("gpc:") or not str(group.get("source") or "").startswith("gs1_gpc_"):
            return {**base, "status": "invalid_product_type", "product_type": None, "product_type_id": product_type_id or None}

        return {
            **base,
            "status": "resolved",
            "product_type": {
                "product_type_id": product_type_id,
                "product_type_name": str(group.get("display_name") or product_type_id),
                "base_unit": str(group.get("default_base_unit") or "stuk"),
                "aggregation_mode": str(group.get("aggregation_mode") or "sum_quantity"),
                "source": str(membership_rows[0].get("source") or group.get("source") or ""),
            },
        }
