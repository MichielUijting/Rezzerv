from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.services.shopping_list_service import (
    add_shopping_list_item,
    complete_active_shopping_list,
    delete_shopping_list_item,
    get_active_shopping_list,
    search_shopping_catalog,
    update_shopping_list_item,
)


def _create_shopping_list_fixture(conn) -> None:
    conn.execute(text("""
        CREATE TABLE shopping_lists (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
            created_at TEXT NOT NULL,
            completed_at TEXT,
            completed_by TEXT
        )
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX ux_shopping_lists_household_active
        ON shopping_lists(household_id)
        WHERE status = 'active'
    """))
    conn.execute(text("""
        CREATE TABLE shopping_list_items (
            id TEXT PRIMARY KEY,
            shopping_list_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            article_name TEXT NOT NULL,
            article_group_name TEXT,
            product_type_name TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_id TEXT,
            quantity NUMERIC,
            volume NUMERIC,
            unit TEXT,
            size TEXT,
            note TEXT,
            checked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(shopping_list_id) REFERENCES shopping_lists(id)
        )
    """))
    conn.execute(text("""
        CREATE INDEX idx_shopping_list_items_active
        ON shopping_list_items(household_id, shopping_list_id, checked, article_name)
    """))


def main() -> int:
    test_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    with test_engine.begin() as conn:
        _create_shopping_list_fixture(conn)
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                aantal INTEGER NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO inventory(id, household_id, naam, aantal)
            VALUES ('inventory-sentinel', '0', 'Voorraad blijft gelijk', 7)
        """))
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_name TEXT NOT NULL,
                article_group_name TEXT,
                product_type_name TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO household_articles(
                id, household_id, article_name, article_group_name, product_type_name
            ) VALUES (
                'household-article-melk', '0', 'Melk', 'Zuivel', 'Halfvolle melk'
            )
        """))
        conn.execute(text("""
            CREATE TABLE article_groups (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO article_groups(id, household_id, name)
            VALUES ('article-group-zuivel', '0', 'Zuivel')
        """))
        conn.execute(text("""
            CREATE TABLE product_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO product_types(id, name)
            VALUES ('product-type-brood', 'Brood')
        """))

        household_results = search_shopping_catalog(
            conn, "0", scope="household_articles", query="mel", limit=20
        )
        assert household_results["total"] == 1, household_results
        assert household_results["items"][0]["article_group_name"] == "Zuivel", household_results
        assert household_results["items"][0]["product_type_name"] == "Halfvolle melk", household_results

        product_type_results = search_shopping_catalog(
            conn, "0", scope="product_types", query="bro", limit=20
        )
        assert product_type_results["total"] == 1, product_type_results
        assert product_type_results["items"][0]["product_type_name"] == "Brood", product_type_results

        article_group_results = search_shopping_catalog(
            conn, "0", scope="article_groups", query="zui", limit=20
        )
        assert article_group_results["total"] == 1, article_group_results
        assert article_group_results["items"][0]["article_group_name"] == "Zuivel", article_group_results

        initial = get_active_shopping_list(conn, "0")
        assert initial["status"] == "active", initial
        assert initial["items"] == [], initial
        first_list_id = initial["id"]

        candidate = household_results["items"][0]
        item = add_shopping_list_item(conn, "0", candidate)
        assert item["household_id"] == "0", item
        assert item["article_name"] == "Melk", item
        assert item["article_group_name"] == "Zuivel", item
        assert item["product_type_name"] == "Halfvolle melk", item
        assert item["source_type"] == "household_article", item
        assert item["source_id"] == "household-article-melk", item
        assert item["quantity"] is None, item
        assert item["volume"] is None, item
        assert item["checked"] is False, item

        other_household = get_active_shopping_list(conn, "1")
        assert other_household["items"] == [], other_household

        updated = update_shopping_list_item(conn, "0", item["id"], {
            "quantity": 2,
            "volume": "1,5",
            "unit": "liter",
            "note": "Halfvol",
            "checked": True,
        })
        assert updated is not None, updated
        assert updated["article_name"] == "Melk", updated
        assert updated["checked"] is True, updated
        assert updated["quantity"] == 2.0, updated
        assert updated["volume"] == 1.5, updated
        assert updated["unit"] == "liter", updated
        assert updated["note"] == "Halfvol", updated

        forbidden_update = update_shopping_list_item(conn, "1", item["id"], {"checked": False})
        assert forbidden_update is None, forbidden_update
        forbidden_delete = delete_shopping_list_item(conn, "1", item["id"])
        assert forbidden_delete is False, forbidden_delete

        active = get_active_shopping_list(conn, "0")
        assert active["item_count"] == 1, active
        assert active["items"][0]["checked"] is True, active

        completed = complete_active_shopping_list(conn, "0", "test-user")
        assert completed["status"] == "completed", completed
        assert completed["completed_list_id"] == first_list_id, completed
        assert completed["completed_item_count"] == 1, completed
        assert completed["active_list_id"] != first_list_id, completed
        assert completed["items"] == [], completed

        next_active = get_active_shopping_list(conn, "0")
        assert next_active["id"] == completed["active_list_id"], next_active
        assert next_active["items"] == [], next_active

        archived_count = conn.execute(text("""
            SELECT COUNT(*) FROM shopping_lists
            WHERE household_id = '0' AND status = 'completed'
        """)).scalar_one()
        assert int(archived_count) == 1, archived_count

        archived_items = conn.execute(text("""
            SELECT COUNT(*) FROM shopping_list_items
            WHERE shopping_list_id = :list_id AND household_id = '0'
        """), {"list_id": first_list_id}).scalar_one()
        assert int(archived_items) == 1, archived_items

        inventory_count = conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar_one()
        inventory_amount = conn.execute(text("""
            SELECT aantal FROM inventory WHERE id = 'inventory-sentinel'
        """)).scalar_one()
        assert int(inventory_count) == 1, inventory_count
        assert int(inventory_amount) == 7, inventory_amount

    print("SHOPPING_LIST_RELEASE_1_SELFTEST=PASS")
    print("catalog_search_three_scopes=PASS")
    print("initial_empty=PASS")
    print("catalog_candidate_and_inline_fields=PASS")
    print("crud_and_checked=PASS")
    print("household_isolation=PASS")
    print("complete_creates_empty_active_list=PASS")
    print("inventory_unchanged=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())