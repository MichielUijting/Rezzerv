"""Uitvoer- en resultaatvalidatie voor de geïsoleerde kassabonketen."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend.app.testing.receipt_inventory_chain_contract import (
    EXPECTED_FINAL_INVENTORY,
    TEST_HOUSEHOLD_ID,
)
from backend.app.testing.receipt_inventory_chain_step3 import (
    current_inventory_quantity,
    process_import_line_to_inventory,
)
from backend.app.testing.receipt_inventory_chain_test_db import (
    FIRST_IMPORT_LINE_ID,
    GLOBAL_PRODUCT_ID,
    SECOND_IMPORT_LINE_ID,
    TEST_GTIN,
    TEST_PRODUCT_TYPE_NAME,
    fetch_one,
    seed_summary,
    temporary_receipt_inventory_chain_database,
)


def validate_isolated_seed(conn) -> None:
    expected = {
        "households": 1,
        "global_products": 1,
        "product_identities": 1,
        "product_inventory_groups": 1,
        "product_group_memberships": 1,
        "household_articles": 1,
        "spaces": 1,
        "sublocations": 1,
        "receipts": 2,
        "receipt_lines": 2,
        "purchase_import_batches": 2,
        "purchase_import_lines": 2,
        "inventory_events": 0,
        "inventory": 0,
    }
    assert seed_summary(conn) == expected

    assert str(conn.execute("select id from households").fetchone()[0]) == TEST_HOUSEHOLD_ID
    for table in (
        "household_articles",
        "spaces",
        "sublocations",
        "receipts",
        "purchase_import_batches",
        "purchase_import_lines",
    ):
        values = {str(row[0]) for row in conn.execute(f"select distinct household_id from {table}")}
        assert values == {TEST_HOUSEHOLD_ID}

    product_link = fetch_one(
        conn,
        """
        select gp.id, gp.primary_gtin, pig.name as product_type
        from global_products gp
        join product_group_memberships pgm on pgm.global_product_id = gp.id
        join product_inventory_groups pig on pig.id = pgm.product_inventory_group_id
        where gp.id = ?
        """,
        (GLOBAL_PRODUCT_ID,),
    )
    assert product_link == {
        "id": GLOBAL_PRODUCT_ID,
        "primary_gtin": TEST_GTIN,
        "product_type": TEST_PRODUCT_TYPE_NAME,
    }


def run_validation() -> dict[str, object]:
    db_path: Path | None = None
    with temporary_receipt_inventory_chain_database() as db:
        db_path = db.path
        validate_isolated_seed(db.conn)

        quantities = [current_inventory_quantity(db.conn)]
        first = process_import_line_to_inventory(db.conn, FIRST_IMPORT_LINE_ID)
        quantities.append(current_inventory_quantity(db.conn))
        second = process_import_line_to_inventory(db.conn, SECOND_IMPORT_LINE_ID)
        quantities.append(current_inventory_quantity(db.conn))
        repeated = process_import_line_to_inventory(db.conn, SECOND_IMPORT_LINE_ID)
        quantities.append(current_inventory_quantity(db.conn))

        assert quantities == [Decimal("0"), Decimal("2"), EXPECTED_FINAL_INVENTORY, EXPECTED_FINAL_INVENTORY]
        assert first["status"] == "processed"
        assert second["status"] == "processed"
        assert repeated["status"] == "already_processed"
        assert db.conn.execute("select count(*) from inventory_events").fetchone()[0] == 2
        assert db.conn.execute("select count(*) from inventory").fetchone()[0] == 1

    assert db_path is not None and not db_path.exists()
    return {
        "status": "passed",
        "household_id": TEST_HOUSEHOLD_ID,
        "inventory_path": ["0", "2", "5", "5"],
        "inventory_event_count": 2,
        "temporary_database_removed": True,
        "idempotent": True,
    }


if __name__ == "__main__":
    print("RECEIPT_INVENTORY_CHAIN_STEP4_GREEN")
    print(run_validation())
