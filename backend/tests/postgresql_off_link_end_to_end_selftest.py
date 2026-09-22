from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine
from app.services.off_product_link_service import link_off_product_with_product_type
from app.services.external_receipt_item_projection import install_receipt_table_line_projection
from app.api import system_routes


TEST_HOUSEHOLD_ID = "__postgresql_off_link_household__"
TEST_PROVIDER_ID = "__postgresql_off_link_provider__"
TEST_PROVIDER_CODE = "postgresql-off-link-e2e"
TEST_CONNECTION_ID = "__postgresql_off_link_connection__"
TEST_BATCH_ID = "__postgresql_off_link_batch__"
TEST_LINE_ID = "__postgresql_off_link_line__"
TEST_CANDIDATE_ID = "__postgresql_off_link_candidate__"
TEST_RECEIPT_ITEM_ID = f"purchase-import-line:{TEST_LINE_ID}"
TEST_CONTEXT_KEY = TEST_RECEIPT_ITEM_ID
TEST_GTIN = "0898965996120"
TEST_GPC_BRICK = "10000284"
TEST_PRODUCT_TYPE = f"gpc:{TEST_GPC_BRICK}"
TEST_RETAILER = "aldi"
TEST_RECEIPT_TEXT = "CHOC OPOPS / CHOCO SHELLS"


def _cleanup(conn) -> None:
    product_ids = [
        str(row[0])
        for row in conn.execute(
            text("SELECT id FROM global_products WHERE primary_gtin = :gtin"),
            {"gtin": TEST_GTIN},
        ).all()
    ]
    for product_id in product_ids:
        conn.execute(
            text("DELETE FROM external_article_product_links WHERE global_product_id = :id"),
            {"id": product_id},
        )
        conn.execute(
            text("DELETE FROM global_product_gpc_bricks WHERE global_product_id = :id"),
            {"id": product_id},
        )
        conn.execute(
            text("DELETE FROM product_group_memberships WHERE global_product_id = :id"),
            {"id": product_id},
        )
        conn.execute(
            text("DELETE FROM product_identities WHERE global_product_id = :id"),
            {"id": product_id},
        )

    conn.execute(
        text("DELETE FROM external_product_candidates WHERE id = :id OR purchase_import_line_id = :line_id"),
        {"id": TEST_CANDIDATE_ID, "line_id": TEST_LINE_ID},
    )
    conn.execute(
        text("DELETE FROM purchase_import_lines WHERE id = :id"),
        {"id": TEST_LINE_ID},
    )
    conn.execute(
        text("DELETE FROM purchase_import_batches WHERE id = :id"),
        {"id": TEST_BATCH_ID},
    )
    conn.execute(
        text("DELETE FROM household_store_connections WHERE id = :id"),
        {"id": TEST_CONNECTION_ID},
    )
    conn.execute(
        text("DELETE FROM store_providers WHERE id = :id OR code = :code"),
        {"id": TEST_PROVIDER_ID, "code": TEST_PROVIDER_CODE},
    )

    for product_id in product_ids:
        conn.execute(
            text("DELETE FROM global_products WHERE id = :id"),
            {"id": product_id},
        )
    conn.execute(
        text(
            "DELETE FROM product_inventory_groups "
            "WHERE inventory_group_key = :inventory_group_key "
            "AND NOT EXISTS ("
            "SELECT 1 FROM product_group_memberships pgm "
            "WHERE pgm.inventory_group_key = product_inventory_groups.inventory_group_key"
            ")"
        ),
        {"inventory_group_key": TEST_PRODUCT_TYPE},
    )


def _seed_realistic_receipt_candidate(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO store_providers (
                id, code, name, status, import_mode, created_at, updated_at
            ) VALUES (
                :id, :code, 'PostgreSQL OFF end-to-end provider',
                'active', 'mock', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {"id": TEST_PROVIDER_ID, "code": TEST_PROVIDER_CODE},
    )
    conn.execute(
        text(
            """
            INSERT INTO household_store_connections (
                id, household_id, store_provider_id,
                connection_status, linked_at, created_at, updated_at
            ) VALUES (
                :id, :household_id, :store_provider_id,
                'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": TEST_CONNECTION_ID,
            "household_id": TEST_HOUSEHOLD_ID,
            "store_provider_id": TEST_PROVIDER_ID,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_batches (
                id, household_id, store_provider_id, connection_id,
                source_type, source_reference,
                import_status, raw_payload, created_at
            ) VALUES (
                :id, :household_id, :store_provider_id, :connection_id,
                'postgresql_off_link_e2e', 'contract:postgresql-off-link-e2e',
                'in_review', '{"retailer_code":"aldi"}', CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": TEST_BATCH_ID,
            "household_id": TEST_HOUSEHOLD_ID,
            "store_provider_id": TEST_PROVIDER_ID,
            "connection_id": TEST_CONNECTION_ID,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, external_article_code,
                article_name_raw, brand_raw, quantity_raw, unit_raw,
                currency_code, match_status, review_decision,
                processing_status, created_at, updated_at
            ) VALUES (
                :id, :batch_id, 'postgresql-off-link-line', NULL,
                :receipt_text, 'PostgreSQL proof', 1, 'stuk',
                'EUR', 'unmatched', 'pending',
                'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": TEST_LINE_ID,
            "batch_id": TEST_BATCH_ID,
            "receipt_text": TEST_RECEIPT_TEXT,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO external_product_candidates (
                id,
                purchase_import_line_id,
                context_key,
                retailer_code,
                receipt_line_text,
                candidate_name,
                candidate_brand,
                candidate_category,
                candidate_source_name,
                candidate_source_product_code,
                source_name,
                source_product_code,
                score,
                status,
                candidate_status,
                is_probable,
                is_user_confirmed,
                is_external_database_override,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :purchase_import_line_id,
                :context_key,
                :retailer_code,
                :receipt_line_text,
                'Chocopops PostgreSQL end-to-end',
                'PostgreSQL proof',
                'Breakfast cereals',
                'open_food_facts',
                :gtin,
                'open_food_facts',
                :gtin,
                0.99,
                'candidate',
                'candidate',
                TRUE,
                FALSE,
                FALSE,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": TEST_CANDIDATE_ID,
            "purchase_import_line_id": TEST_LINE_ID,
            "context_key": TEST_CONTEXT_KEY,
            "retailer_code": TEST_RETAILER,
            "receipt_line_text": TEST_RECEIPT_TEXT,
            "gtin": TEST_GTIN,
        },
    )


def main() -> None:
    inventory_before = 0
    events_before = 0
    with engine.begin() as conn:
        _cleanup(conn)
        inventory_before = int(conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar() or 0)
        events_before = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar() or 0)
        _seed_realistic_receipt_candidate(conn)

    off_product = {
        "gtin": TEST_GTIN,
        "product_name": "Chocopops PostgreSQL end-to-end",
        "brand": "PostgreSQL proof",
        "category": "Breakfast cereals",
        "quantity": "375 g",
        "image_url": "https://images.openfoodfacts.test/0898965996120.jpg",
    }
    product_type_assignment = {
        "product_type_id": TEST_PRODUCT_TYPE,
        "gpc_source": "manual",
        "confidence_score": 1.0,
    }

    global_product_id = ""
    try:
        result = link_off_product_with_product_type(
            receipt_item_id=TEST_RECEIPT_ITEM_ID,
            off_product=off_product,
            product_type_assignment=product_type_assignment,
        )
        if not result.get("ok") or not result.get("linked"):
            raise AssertionError(result)
        global_product_id = str((result.get("global_product") or {}).get("id") or "")
        if not global_product_id:
            raise AssertionError(result)
        receipt_item = result.get("receipt_item") or {}
        if receipt_item.get("receipt_item_type") != "purchase_import_line":
            raise AssertionError(receipt_item)

        with engine.begin() as conn:
            line = conn.execute(
                text(
                    """
                    SELECT matched_global_product_id, match_status
                    FROM purchase_import_lines
                    WHERE id = :id
                    """
                ),
                {"id": TEST_LINE_ID},
            ).mappings().one()
            if line.get("matched_global_product_id") not in (None, ""):
                raise AssertionError(line)
            if str(line.get("match_status") or "") != "unmatched":
                raise AssertionError(line)

            candidate = conn.execute(
                text(
                    """
                    SELECT global_product_id, retailer_code, receipt_line_text
                    FROM external_product_candidates
                    WHERE id = :id
                    """
                ),
                {"id": TEST_CANDIDATE_ID},
            ).mappings().one()
            if candidate.get("global_product_id") not in (None, ""):
                raise AssertionError(candidate)
            if candidate.get("retailer_code") != TEST_RETAILER:
                raise AssertionError(candidate)

            membership = conn.execute(
                text(
                    """
                    SELECT active, confirmed_by_user
                    FROM product_group_memberships
                    WHERE global_product_id = :global_product_id
                      AND inventory_group_key = :inventory_group_key
                    """
                ),
                {
                    "global_product_id": global_product_id,
                    "inventory_group_key": TEST_PRODUCT_TYPE,
                },
            ).mappings().one()
            if int(membership.get("active") or 0) != 1:
                raise AssertionError(membership)
            if int(membership.get("confirmed_by_user") or 0) != 1:
                raise AssertionError(membership)

            gpc = conn.execute(
                text(
                    """
                    SELECT brick_code, assignment_source
                    FROM global_product_gpc_bricks
                    WHERE global_product_id = :global_product_id
                    """
                ),
                {"global_product_id": global_product_id},
            ).mappings().one()
            if gpc.get("brick_code") != TEST_GPC_BRICK:
                raise AssertionError(gpc)
            if gpc.get("assignment_source") != "manual":
                raise AssertionError(gpc)

            external_link = conn.execute(
                text(
                    """
                    SELECT retailer_code, receipt_text_normalized, global_product_id, status
                    FROM external_article_product_links
                    WHERE global_product_id = :global_product_id
                    ORDER BY confirmed_at DESC
                    LIMIT 1
                    """
                ),
                {"global_product_id": global_product_id},
            ).mappings().one()
            if external_link.get("retailer_code") != TEST_RETAILER:
                raise AssertionError(external_link)
            if external_link.get("receipt_text_normalized") != "choc opops choco shells":
                raise AssertionError(external_link)
            if external_link.get("status") != "confirmed":
                raise AssertionError(external_link)

            inventory_after = int(conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar() or 0)
            events_after = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar() or 0)
            if inventory_after != inventory_before or events_after != events_before:
                raise AssertionError(
                    {
                        "inventory_before": inventory_before,
                        "inventory_after": inventory_after,
                        "events_before": events_before,
                        "events_after": events_after,
                    }
                )

        repeat_result = link_off_product_with_product_type(
            receipt_item_id=TEST_RECEIPT_ITEM_ID,
            off_product=off_product,
            product_type_assignment=product_type_assignment,
        )
        repeat_global_product_id = str(
            (repeat_result.get("global_product") or {}).get("id") or ""
        )
        if repeat_global_product_id != global_product_id:
            raise AssertionError(
                {
                    "first_global_product_id": global_product_id,
                    "repeat_global_product_id": repeat_global_product_id,
                    "repeat_result": repeat_result,
                }
            )

        with engine.begin() as conn:
            confirmed_links = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM external_article_product_links
                        WHERE retailer_code = :retailer_code
                          AND receipt_text_normalized = :receipt_text_normalized
                          AND status = 'confirmed'
                        """
                    ),
                    {
                        "retailer_code": TEST_RETAILER,
                        "receipt_text_normalized": "choc opops choco shells",
                    },
                ).scalar()
                or 0
            )
            inactive_links = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM external_article_product_links
                        WHERE retailer_code = :retailer_code
                          AND receipt_text_normalized = :receipt_text_normalized
                          AND status = 'inactive'
                        """
                    ),
                    {
                        "retailer_code": TEST_RETAILER,
                        "receipt_text_normalized": "choc opops choco shells",
                    },
                ).scalar()
                or 0
            )
            membership_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM product_group_memberships
                        WHERE global_product_id = :global_product_id
                          AND inventory_group_key = :inventory_group_key
                        """
                    ),
                    {
                        "global_product_id": global_product_id,
                        "inventory_group_key": TEST_PRODUCT_TYPE,
                    },
                ).scalar()
                or 0
            )
            gpc_assignment_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM global_product_gpc_bricks
                        WHERE global_product_id = :global_product_id
                          AND brick_code = :brick_code
                        """
                    ),
                    {
                        "global_product_id": global_product_id,
                        "brick_code": TEST_GPC_BRICK,
                    },
                ).scalar()
                or 0
            )
            inventory_after_repeat = int(
                conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar() or 0
            )
            events_after_repeat = int(
                conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar() or 0
            )

        if confirmed_links != 1:
            raise AssertionError({"confirmed_links": confirmed_links})
        if inactive_links < 1:
            raise AssertionError({"inactive_links": inactive_links})
        if membership_count != 1:
            raise AssertionError({"membership_count": membership_count})
        if gpc_assignment_count != 1:
            raise AssertionError({"gpc_assignment_count": gpc_assignment_count})
        if inventory_after_repeat != inventory_before or events_after_repeat != events_before:
            raise AssertionError(
                {
                    "inventory_before": inventory_before,
                    "inventory_after_repeat": inventory_after_repeat,
                    "events_before": events_before,
                    "events_after_repeat": events_after_repeat,
                }
            )

        print("POSTGRESQL_OFF_LINK_PURCHASE_IMPORT_SOURCE_UNCHANGED_GREEN")
        print("POSTGRESQL_OFF_LINK_GPC_ASSIGNMENT_GREEN")
        print("POSTGRESQL_OFF_LINK_EXTERNAL_ARTICLE_CONFIRMATION_GREEN")
        print("POSTGRESQL_OFF_LINK_NO_INVENTORY_MUTATION_GREEN")
        print("POSTGRESQL_OFF_LINK_REPEAT_IDEMPOTENT_GREEN")

        install_receipt_table_line_projection()
        receipt_items_payload = system_routes.external_databases_receipt_items(limit=500)
        receipt_items = [
            item
            for item in list(receipt_items_payload.get("items") or [])
            if isinstance(item, dict)
        ]
        linked_receipt_item = next(
            (
                item
                for item in receipt_items
                if str(item.get("global_product_id") or item.get("central_global_product_id") or "").strip()
                == global_product_id
            ),
            None,
        )
        if linked_receipt_item is None:
            raise AssertionError(
                {
                    "reason": "linked Chocopops product missing from receipt-items projection",
                    "global_product_id": global_product_id,
                    "items": receipt_items,
                }
            )
        projected_product_type = str(
            linked_receipt_item.get("product_type_id")
            or linked_receipt_item.get("inventory_group_key")
            or ""
        ).strip()
        if projected_product_type != TEST_PRODUCT_TYPE:
            raise AssertionError(
                {
                    "reason": "receipt-items projection lost GPC product type",
                    "expected": TEST_PRODUCT_TYPE,
                    "actual": projected_product_type,
                    "item": linked_receipt_item,
                }
            )
        print("POSTGRESQL_OFF_LINK_RECEIPT_ITEMS_API_LOAD_GREEN")

        from postgresql_off_link_receipt_table_end_to_end_selftest import (
            main as run_receipt_table_end_to_end,
        )

        run_receipt_table_end_to_end()
        print("POSTGRESQL_OFF_LINK_END_TO_END_SELFTEST_GREEN")
    finally:
        with engine.begin() as conn:
            _cleanup(conn)


if __name__ == "__main__":
    main()