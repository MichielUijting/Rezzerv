from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.off_product_link_service import (
    _assert_receipt_item_household,
    _clean_text,
    _link_receipt_item,
    _normalize_gtin,
    _upsert_global_product,
)


def save_barcode_receipt_item(
    *,
    household_id: str,
    receipt_item_id: str,
    gtin: str,
    article_name: str,
) -> dict[str, Any]:
    """Sla een barcode centraal op en koppel alleen het kassabonartikel.

    Deze workflow muteert geen voorraad en voert daarom geen volledige
    inventory_events-tellingen uit tijdens een gebruikersactie.
    """

    normalized_gtin = _normalize_gtin(gtin)
    normalized_article_name = (
        _clean_text(article_name) or f"Product {normalized_gtin}"
    )
    normalized_receipt_item_id = _clean_text(receipt_item_id)

    with engine.begin() as conn:
        _assert_receipt_item_household(
            conn,
            receipt_item_id=normalized_receipt_item_id,
            household_id=household_id,
        )

        global_product_id, stored_gtin, _, _ = _upsert_global_product(
            conn,
            {
                "gtin": normalized_gtin,
                "product_name": normalized_article_name,
            },
            source_name="barcode_scan",
        )

        receipt_link = _link_receipt_item(
            conn,
            normalized_receipt_item_id,
            global_product_id,
            link_household_article=False,
        )

        product = conn.execute(
            text(
                """
                SELECT id, name, brand, status, primary_gtin
                FROM global_products
                WHERE id = :global_product_id
                LIMIT 1
                """
            ),
            {"global_product_id": global_product_id},
        ).mappings().first()

        return {
            "ok": True,
            "gtin": stored_gtin,
            "product": {
                "global_product_id": global_product_id,
                "name": (
                    product.get("name")
                    if product
                    else normalized_article_name
                ),
                "brand": product.get("brand") if product else None,
                "status": product.get("status") if product else "active",
                "primary_gtin": (
                    product.get("primary_gtin")
                    if product
                    else stored_gtin
                ),
            },
            "receipt_item": receipt_link,
            "inventory_mutated": False,
            "creates_inventory_event": False,
        }
