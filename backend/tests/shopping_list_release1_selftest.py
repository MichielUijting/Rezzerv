from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.shopping_list_service import (
    add_shopping_list_item,
    complete_active_shopping_list,
    delete_shopping_list_item,
    get_active_shopping_list,
    update_shopping_list_item,
)


def main() -> int:
    test_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    with test_engine.begin() as conn:
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

        initial = get_active_shopping_list(conn, "0")
        assert initial["status"] == "active", initial
        assert initial["items"] == [], initial
        first_list_id = initial["id"]

        item = add_shopping_list_item(conn, "0", {
            "article_name": "Melk",
            "quantity": 2,
            "volume": "1,5",
            "unit": "liter",
            "note": "Halfvol",
        })
        assert item["household_id"] == "0", item
        assert item["quantity"] == 2.0, item
        assert item["volume"] == 1.5, item
        assert item["checked"] is False, item

        other_household = get_active_shopping_list(conn, "1")
        assert other_household["items"] == [], other_household

        updated = update_shopping_list_item(conn, "0", item["id"], {
            "article_name": "Halfvolle melk",
            "checked": True,
        })
        assert updated is not None, updated
        assert updated["article_name"] == "Halfvolle melk", updated
        assert updated["checked"] is True, updated
        assert updated["quantity"] == 2.0, updated

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
    print("initial_empty=PASS")
    print("crud_and_checked=PASS")
    print("household_isolation=PASS")
    print("complete_creates_empty_active_list=PASS")
    print("inventory_unchanged=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
