from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema
from app.services.product_type_household_settings_service import (
    EXTENDED_COLUMNS,
    analyze_household_article_settings_migration,
    ensure_extended_product_type_settings_schema,
    list_extended_product_type_settings,
    upsert_extended_product_type_setting,
)

HOUSEHOLD_ID = "__product_type_settings_c1_c2__"
PRODUCT_TYPE_ID = "gpc:99999999"


def _table_count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM household_product_type_settings WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :product_type_id"),
            {"product_type_id": PRODUCT_TYPE_ID},
        )


def main() -> None:
    ensure_product_inventory_group_schema()
    ensure_extended_product_type_settings_schema()
    _cleanup()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO product_inventory_groups (
                        inventory_group_key, display_name, default_base_unit,
                        aggregation_mode, active, source, created_at, updated_at
                    ) VALUES (
                        :key, 'C1 C2 testtype', 'ml', 'sum_quantity', 1,
                        'gs1_gpc_selftest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"key": PRODUCT_TYPE_ID},
            )
            if str(engine.dialect.name or "").lower() == "sqlite":
                columns = {str(row[1]) for row in conn.execute(text("PRAGMA table_info(household_product_type_settings)")).all()}
            else:
                columns = {
                    str(row[0])
                    for row in conn.execute(
                        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'household_product_type_settings'")
                    ).all()
                }
        missing_columns = sorted(set(EXTENDED_COLUMNS) - columns)
        assert not missing_columns, missing_columns
        print("PASS product_type_extended_settings_schema")

        saved = upsert_extended_product_type_setting(
            household_id=HOUSEHOLD_ID,
            product_type_id=PRODUCT_TYPE_ID,
            payload={
                "min_stock": 2000,
                "ideal_stock": 6000,
                "consumable": True,
                "status": "active",
                "favorite_store": "Jumbo",
                "average_price": 1.29,
                "auto_restock": True,
                "packaging_unit": "pak",
                "packaging_quantity": 1000,
                "notes": "Alleen lactosevrij",
            },
        )
        setting = saved["setting"]
        assert setting["min_stock"] == 2000
        assert setting["ideal_stock"] == 6000
        assert setting["favorite_store"] == "Jumbo"
        assert setting["status"] == "active"
        assert setting["auto_restock"] == 1
        assert setting["packaging_unit"] == "pak"
        assert setting["packaging_quantity"] == 1000
        print("PASS product_type_extended_settings_roundtrip")

        listed = list_extended_product_type_settings(HOUSEHOLD_ID)
        assert listed["basis"] == "product_type"
        assert len(listed["items"]) == 1
        assert listed["items"][0]["notes"] == "Alleen lactosevrij"
        print("PASS product_type_extended_settings_list")

        try:
            upsert_extended_product_type_setting(
                household_id=HOUSEHOLD_ID,
                product_type_id=PRODUCT_TYPE_ID,
                payload={"min_stock": 10, "ideal_stock": 9},
            )
            raise AssertionError("Ongeldige streefvoorraad werd geaccepteerd")
        except ValueError as exc:
            assert "Streefvoorraad" in str(exc)

        try:
            upsert_extended_product_type_setting(
                household_id=HOUSEHOLD_ID,
                product_type_id=PRODUCT_TYPE_ID,
                payload={"packaging_quantity": 1000},
            )
            raise AssertionError("Verpakkingshoeveelheid zonder eenheid werd geaccepteerd")
        except ValueError as exc:
            assert "Verpakkingseenheid" in str(exc)
        print("PASS product_type_extended_settings_validation")

        with engine.begin() as conn:
            before = {
                "household_product_type_settings": _table_count(conn, "household_product_type_settings"),
                "household_article_settings": _table_count(conn, "household_article_settings"),
                "household_articles": _table_count(conn, "household_articles"),
            }
        analysis = analyze_household_article_settings_migration(HOUSEHOLD_ID)
        assert analysis["read_only"] is True
        assert analysis["household_id"] == HOUSEHOLD_ID
        with engine.begin() as conn:
            after = {
                "household_product_type_settings": _table_count(conn, "household_product_type_settings"),
                "household_article_settings": _table_count(conn, "household_article_settings"),
                "household_articles": _table_count(conn, "household_articles"),
            }
        assert before == after, {"before": before, "after": after}
        print("PASS product_type_migration_analysis_read_only")

        print("PRODUCT_TYPE_ALMOST_OUT_PHASE_C1_C2_GREEN")
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
