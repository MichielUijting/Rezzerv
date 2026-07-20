"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Stap 3 kassabon -> Uitpakken -> Voorraad-ketentest
- Runtime Type: test
- Status Authority: no
- Refactor Status: keep_test

Deze stap verwerkt de twee geïsoleerde kassabonfixtures naar voorraad en
bewijst dat herverwerking van dezelfde tweede bon geen dubbele voorraadmutatie
veroorzaakt. Productiecode en de normale runtime-database worden niet geraakt.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.testing.receipt_inventory_chain_contract import (
    EXPECTED_FINAL_INVENTORY,
    FIRST_RECEIPT,
    SECOND_RECEIPT,
    TEST_HOUSEHOLD_ID,
)
from backend.app.testing.receipt_inventory_chain_test_db import (
    FIRST_IMPORT_LINE_ID,
    GLOBAL_PRODUCT_ID,
    HOUSEHOLD_ARTICLE_ID,
    LOCATION_ID,
    SECOND_IMPORT_LINE_ID,
    SUBLOCATION_ID,
    fetch_one,
    temporary_receipt_inventory_chain_database,
    utc_now,
    validate_seed,
)


def decimal_value(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def current_inventory_quantity(conn: sqlite3.Connection) -> Decimal:
    row = fetch_one(
        conn,
        """
        select quantity
        from inventory
        where household_id = ?
          and household_article_id = ?
          and location_id = ?
          and sublocation_id = ?
        """,
        (
            TEST_HOUSEHOLD_ID,
            HOUSEHOLD_ARTICLE_ID,
            LOCATION_ID,
            SUBLOCATION_ID,
        ),
    )
    return decimal_value(row["quantity"] if row else 0)


def process_import_line_to_inventory(
    conn: sqlite3.Connection,
    import_line_id: int,
) -> dict[str, Any]:
    """Verwerk één Uitpakken-regel transactioneel en idempotent."""

    line = fetch_one(
        conn,
        """
        select
            pil.id,
            pil.household_id,
            pil.matched_household_article_id,
            pil.target_location_id,
            pil.target_sublocation_id,
            pil.quantity,
            pil.status,
            pil.processed_event_id,
            ha.global_product_id
        from purchase_import_lines pil
        join household_articles ha on ha.id = pil.matched_household_article_id
        where pil.id = ?
        """,
        (import_line_id,),
    )
    if line is None:
        raise AssertionError(f"Uitpakken-regel {import_line_id} ontbreekt")

    if str(line["household_id"]) != TEST_HOUSEHOLD_ID:
        raise AssertionError("Ketenverwerking mag uitsluitend huishouden 0 gebruiken")
    if int(line["global_product_id"]) != GLOBAL_PRODUCT_ID:
        raise AssertionError("Uitpakken-regel is niet aan het afgesproken globale product gekoppeld")
    if line["target_location_id"] is None or line["target_sublocation_id"] is None:
        raise AssertionError("Doellocatie en sublocatie zijn verplicht")

    existing_event = fetch_one(
        conn,
        """
        select id, quantity_delta
        from inventory_events
        where source_type = 'purchase_import_line'
          and source_id = ?
        """,
        (import_line_id,),
    )
    if existing_event is not None:
        return {
            "status": "already_processed",
            "import_line_id": import_line_id,
            "event_id": int(existing_event["id"]),
            "quantity_delta": decimal_value(existing_event["quantity_delta"]),
            "inventory_quantity": current_inventory_quantity(conn),
        }

    quantity = decimal_value(line["quantity"])
    if quantity <= 0:
        raise AssertionError("Voorraadmutatie moet groter dan nul zijn")

    now = utc_now()
    try:
        conn.execute("begin")
        cursor = conn.execute(
            """
            insert into inventory_events (
                household_id,
                household_article_id,
                source_type,
                source_id,
                quantity_delta,
                location_id,
                sublocation_id,
                occurred_at
            ) values (?, ?, 'purchase_import_line', ?, ?, ?, ?, ?)
            """,
            (
                TEST_HOUSEHOLD_ID,
                HOUSEHOLD_ARTICLE_ID,
                import_line_id,
                str(quantity),
                LOCATION_ID,
                SUBLOCATION_ID,
                now,
            ),
        )
        event_id = int(cursor.lastrowid)

        conn.execute(
            """
            insert into inventory (
                household_id,
                household_article_id,
                location_id,
                sublocation_id,
                quantity,
                updated_at
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(household_id, household_article_id, location_id, sublocation_id)
            do update set
                quantity = inventory.quantity + excluded.quantity,
                updated_at = excluded.updated_at
            """,
            (
                TEST_HOUSEHOLD_ID,
                HOUSEHOLD_ARTICLE_ID,
                LOCATION_ID,
                SUBLOCATION_ID,
                str(quantity),
                now,
            ),
        )
        conn.execute(
            """
            update purchase_import_lines
            set status = 'processed', processed_event_id = ?
            where id = ?
            """,
            (event_id, import_line_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "status": "processed",
        "import_line_id": import_line_id,
        "event_id": event_id,
        "quantity_delta": quantity,
        "inventory_quantity": current_inventory_quantity(conn),
    }


def run_step3_chain() -> dict[str, Any]:
    """Voer 0 -> 2 -> 5 -> 5 uit en retourneer het bewijsrapport."""

    db_path: Path | None = None
    with temporary_receipt_inventory_chain_database() as db:
        db_path = db.path
        validate_seed(db.conn)

        initial_quantity = current_inventory_quantity(db.conn)
        first_result = process_import_line_to_inventory(db.conn, FIRST_IMPORT_LINE_ID)
        quantity_after_first = current_inventory_quantity(db.conn)
        second_result = process_import_line_to_inventory(db.conn, SECOND_IMPORT_LINE_ID)
        quantity_after_second = current_inventory_quantity(db.conn)
        repeated_second_result = process_import_line_to_inventory(db.conn, SECOND_IMPORT_LINE_ID)
        quantity_after_repeat = current_inventory_quantity(db.conn)

        event_count = int(
            db.conn.execute(
                "select count(*) from inventory_events where source_type = 'purchase_import_line'"
            ).fetchone()[0]
        )
        processed_line_count = int(
            db.conn.execute(
                "select count(*) from purchase_import_lines where status = 'processed'"
            ).fetchone()[0]
        )

        assert initial_quantity == Decimal("0")
        assert first_result["status"] == "processed"
        assert first_result["quantity_delta"] == FIRST_RECEIPT.quantity
        assert quantity_after_first == Decimal("2")
        assert second_result["status"] == "processed"
        assert second_result["quantity_delta"] == SECOND_RECEIPT.quantity
        assert quantity_after_second == EXPECTED_FINAL_INVENTORY
        assert repeated_second_result["status"] == "already_processed"
        assert quantity_after_repeat == EXPECTED_FINAL_INVENTORY
        assert event_count == 2
        assert processed_line_count == 2

        report = {
            "status": "passed",
            "household_id": TEST_HOUSEHOLD_ID,
            "inventory_path": [
                str(initial_quantity),
                str(quantity_after_first),
                str(quantity_after_second),
                str(quantity_after_repeat),
            ],
            "first_receipt": first_result,
            "second_receipt": second_result,
            "repeated_second_receipt": repeated_second_result,
            "inventory_event_count": event_count,
            "processed_import_line_count": processed_line_count,
            "idempotent": True,
        }

    assert db_path is not None and not db_path.exists()
    report["temporary_database_removed"] = True
    return report


if __name__ == "__main__":
    result = run_step3_chain()
    print("RECEIPT_INVENTORY_CHAIN_STEP3_GREEN")
    print(result)
