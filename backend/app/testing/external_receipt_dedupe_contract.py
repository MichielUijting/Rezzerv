"""Regressiecontract voor initiële Catalogusprojectie bij dubbele bonregels."""

from app.services.external_product_candidate_store import (
    _m2c2i_fix7b_dedupe_top_receipt_items,
)


def run() -> None:
    rows = [
        {
            "receipt_line_text": "SYNTHETISCH PRODUCT",
            "retailer_code": "voorbeeldwinkel",
            "status": "no_candidate",
            "candidate_status": "no_candidate",
            "global_product_id": None,
            "updated_at": "2026-01-02T12:00:00",
            "candidates": [],
        },
        {
            "receipt_line_text": "SYNTHETISCH PRODUCT",
            "retailer_code": "voorbeeldwinkel",
            "status": "linked_to_catalog",
            "candidate_status": "linked_to_catalog",
            "global_product_id": "synthetic-global-product-id",
            "canonical_catalog_product_id": "synthetic-global-product-id",
            "linked_candidate_name": "Synthetisch product",
            "linked_gtin": "12345670",
            "linked_product_type": "Nog niet geclassificeerd",
            "is_linked_to_catalog": True,
            "is_existing_link_for_receipt_item": True,
            "updated_at": "2026-01-01T12:00:00",
            "candidates": [],
        },
    ]

    result = _m2c2i_fix7b_dedupe_top_receipt_items(rows)

    assert len(result) == 1
    row = result[0]
    assert row["global_product_id"] == "synthetic-global-product-id"
    assert row["canonical_catalog_product_id"] == (
        "synthetic-global-product-id"
    )
    assert row["linked_candidate_name"] == "Synthetisch product"
    assert row["linked_gtin"] == "12345670"
    assert row["status"] == "linked_to_catalog"
    assert row["is_linked_to_catalog"] is True

    print("EXTERNAL_RECEIPT_INITIAL_PROJECTION_CONTRACT_GREEN")


if __name__ == "__main__":
    run()
