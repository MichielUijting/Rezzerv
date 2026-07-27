from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import engine
from app.services.product_type_almost_out_service import (
    build_product_type_almost_out_preview,
    ensure_household_product_type_settings_schema,
    upsert_household_product_type_setting,
)


def main() -> int:
    ensure_household_product_type_settings_schema()
    suffix = uuid.uuid4().hex
    household_id = f"product-type-almost-out-{suffix}"
    product_type_id = f"gpc:{uuid.uuid4().int % 10**8:08d}"
    article_a = f"pta-article-a-{suffix}"
    article_b = f"pta-article-b-{suffix}"
    product_a = f"pta-product-a-{suffix}"
    product_b = f"pta-product-b-{suffix}"
    inventory_a = f"pta-inventory-a-{suffix}"
    inventory_b = f"pta-inventory-b-{suffix}"

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO product_inventory_groups (
                        inventory_group_key, display_name, default_base_unit,
                        aggregation_mode, active, source, created_at, updated_at
                    ) VALUES (
                        :key, 'Halfvolle melk contracttest', 'ml',
                        'volume', 1, 'gs1_gpc_selftest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"key": product_type_id},
            )
            for article_id, name, old_minimum in (
                (article_a, "Merk A halfvolle melk", 99),
                (article_b, "Merk B halfvolle melk", 1),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO household_articles (
                            id, household_id, naam, consumable,
                            min_stock, ideal_stock, status, updated_at
                        ) VALUES (
                            :id, :household_id, :name, 1,
                            :min_stock, :ideal_stock, 'active', CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": article_id,
                        "household_id": household_id,
                        "name": name,
                        "min_stock": old_minimum,
                        "ideal_stock": old_minimum + 1,
                    },
                )
            for article_id, product_id, gtin in (
                (article_a, product_a, f"98{uuid.uuid4().int % 10**11:011d}"),
                (article_b, product_b, f"97{uuid.uuid4().int % 10**11:011d}"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO product_identities (
                            id, household_article_id, global_product_id,
                            identity_type, identity_value, source,
                            confidence_score, is_primary, created_at, updated_at
                        ) VALUES (
                            :id, :article_id, :product_id,
                            'gtin', :gtin, 'product_type_almost_out_selftest',
                            1.0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "article_id": article_id,
                        "product_id": product_id,
                        "gtin": gtin,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO product_group_memberships (
                            id, global_product_id, inventory_group_key,
                            confidence, source, confirmed_by_user,
                            active, created_at, updated_at
                        ) VALUES (
                            :id, :product_id, :product_type_id,
                            1.0, 'product_type_almost_out_selftest', 1,
                            1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "product_id": product_id,
                        "product_type_id": product_type_id,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO product_unit_conversions (
                        id, global_product_id, inventory_group_key,
                        content_value, content_unit, base_quantity, base_unit,
                        confidence, source, created_at, updated_at
                    ) VALUES (
                        :id, :product_id, :product_type_id,
                        1, 'l', 1000, 'ml',
                        1.0, 'product_type_almost_out_selftest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": str(uuid.uuid4()), "product_id": product_a, "product_type_id": product_type_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO product_unit_conversions (
                        id, global_product_id, inventory_group_key,
                        content_value, content_unit, base_quantity, base_unit,
                        confidence, source, created_at, updated_at
                    ) VALUES (
                        :id, :product_id, :product_type_id,
                        500, 'ml', 500, 'ml',
                        1.0, 'product_type_almost_out_selftest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": str(uuid.uuid4()), "product_id": product_b, "product_type_id": product_type_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO inventory (
                        id, naam, aantal, household_id,
                        household_article_id, status, updated_at
                    ) VALUES (
                        :id, 'Merk A halfvolle melk', 1, :household_id,
                        :article_id, 'active', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": inventory_a, "household_id": household_id, "article_id": article_a},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO inventory (
                        id, naam, aantal, household_id,
                        household_article_id, status, updated_at
                    ) VALUES (
                        :id, 'Merk B halfvolle melk', 2, :household_id,
                        :article_id, 'active', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": inventory_b, "household_id": household_id, "article_id": article_b},
            )

        saved = upsert_household_product_type_setting(
            household_id=household_id,
            product_type_id=product_type_id,
            min_stock=2500,
            ideal_stock=5000,
            consumable=True,
            active=True,
        )
        assert saved.get("ok") is True, saved

        preview = build_product_type_almost_out_preview(household_id)
        assert preview.get("basis") == "product_type", preview
        assert preview.get("read_only") is True, preview
        items = preview.get("items") or []
        assert len(items) == 1, items
        item = items[0]
        assert item.get("product_type_id") == product_type_id, item
        assert abs(float(item.get("current_quantity") or 0) - 2000.0) < 0.000001, item
        assert abs(float(item.get("amount_to_buy") or 0) - 3000.0) < 0.000001, item
        assert item.get("include_in_almost_out") is True, item
        assert item.get("reason") == "below_or_equal_minimum", item
        assert item.get("data_state") == "ok", item
        assert int(item.get("contributing_articles") or 0) == 2, item
        assert int(item.get("contributing_inventory_rows") or 0) == 2, item
        assert item.get("excluded_inventory_rows") == [], item

        # De oude, onderling conflicterende artikelminima (99 en 1) mogen de
        # Producttype-uitkomst niet bepalen.
        assert float(item.get("min_stock")) == 2500.0, item
        print("PASS product_type_settings_contract")
        print("PASS product_type_multi_article_aggregation")
        print("PASS product_type_unit_conversion")
        print("PASS legacy_article_thresholds_ignored")
        print("PRODUCT_TYPE_ALMOST_OUT_PHASE_AB_GREEN")
        return 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM household_product_type_settings WHERE household_id = :household_id"), {"household_id": household_id})
            conn.execute(text("DELETE FROM inventory WHERE id IN (:a, :b)"), {"a": inventory_a, "b": inventory_b})
            conn.execute(text("DELETE FROM product_unit_conversions WHERE global_product_id IN (:a, :b)"), {"a": product_a, "b": product_b})
            conn.execute(text("DELETE FROM product_group_memberships WHERE global_product_id IN (:a, :b)"), {"a": product_a, "b": product_b})
            conn.execute(text("DELETE FROM product_identities WHERE household_article_id IN (:a, :b)"), {"a": article_a, "b": article_b})
            conn.execute(text("DELETE FROM household_articles WHERE id IN (:a, :b)"), {"a": article_a, "b": article_b})
            conn.execute(text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :key"), {"key": product_type_id})


if __name__ == "__main__":
    raise SystemExit(main())
