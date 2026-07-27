from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_product_link_service import (
    ensure_external_article_product_link_schema,
)
from app.services.gpc_localization_service import ensure_gpc_localization_schema
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def audit_linked_receipt_article_product_types() -> dict[str, Any]:
    """Controleer alle bevestigde kassabonartikelkoppelingen zonder gegevens te wijzigen.

    De gezaghebbende scope is external_article_product_links met status confirmed.
    Iedere rij moet verwijzen naar een bestaand universeel artikel, exact één actief
    officieel GPC Brick-Producttype en een Nederlandse Brick-omschrijving.
    """
    ensure_product_inventory_group_schema()
    ensure_gpc_localization_schema()

    with engine.begin() as conn:
        ensure_external_article_product_link_schema(conn)
        rows = conn.execute(text("""
            SELECT
                eapl.id AS link_id,
                eapl.retailer_code,
                eapl.receipt_text_normalized,
                eapl.external_article_code,
                eapl.global_product_id,
                COALESCE(gp.name, '') AS global_product_name,
                COALESCE(gp.brand, '') AS global_product_brand,
                COALESCE(gp.primary_gtin, '') AS primary_gtin,
                COALESCE(pgm.inventory_group_key, '') AS product_type_id,
                COALESCE(gpc.gpc_brick_code, '') AS gpc_brick_code,
                COALESCE(gpc.gpc_brick_name_nl, '') AS gpc_brick_name_nl,
                COALESCE(gpc.gpc_brick_name_en, '') AS gpc_brick_name_en,
                COALESCE(gpc.source_version, '') AS gpc_source_version
            FROM external_article_product_links eapl
            LEFT JOIN global_products gp
              ON gp.id = eapl.global_product_id
            LEFT JOIN product_group_memberships pgm
              ON pgm.global_product_id = eapl.global_product_id
             AND COALESCE(pgm.active, 1) = 1
             AND pgm.inventory_group_key LIKE 'gpc:%'
            LEFT JOIN gpc_product_groups gpc
              ON gpc.gpc_brick_code = substr(pgm.inventory_group_key, 5)
             AND COALESCE(gpc.active, 1) = 1
            WHERE eapl.status = 'confirmed'
            ORDER BY
                lower(COALESCE(eapl.retailer_code, '')),
                lower(COALESCE(eapl.receipt_text_normalized, '')),
                lower(COALESCE(eapl.external_article_code, '')),
                eapl.id
        """)).mappings().all()

    items: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        product_id = _clean(row.get("global_product_id"))
        product_type_id = _clean(row.get("product_type_id"))
        brick_code = _clean(row.get("gpc_brick_code"))
        name_nl = _clean(row.get("gpc_brick_name_nl"))
        name_en = _clean(row.get("gpc_brick_name_en"))

        if not product_id or not _clean(row.get("global_product_name")):
            status = "missing_global_product"
        elif not product_type_id:
            status = "missing_product_type"
        elif not brick_code:
            status = "invalid_product_type"
        elif not name_nl:
            status = "missing_dutch_description"
        elif not name_en:
            status = "missing_english_description"
        else:
            status = "complete"

        row["status"] = status
        row["product_type_label"] = name_nl
        items.append(row)

    summary = {
        "linked_receipt_articles": len(items),
        "unique_global_products": len({_clean(item.get("global_product_id")) for item in items if _clean(item.get("global_product_id"))}),
        "complete": sum(1 for item in items if item["status"] == "complete"),
        "missing_global_product": sum(1 for item in items if item["status"] == "missing_global_product"),
        "missing_product_type": sum(1 for item in items if item["status"] == "missing_product_type"),
        "invalid_product_type": sum(1 for item in items if item["status"] == "invalid_product_type"),
        "missing_dutch_description": sum(1 for item in items if item["status"] == "missing_dutch_description"),
        "missing_english_description": sum(1 for item in items if item["status"] == "missing_english_description"),
    }
    summary["all_complete"] = bool(items) and summary["complete"] == len(items)

    return {
        "ok": True,
        "scope": "confirmed_external_article_product_links",
        "basis": "receipt_article_to_global_product_to_gpc_brick",
        "read_only": True,
        "mutates_inventory": False,
        "display_language": "nl",
        "items": items,
        "summary": summary,
    }
