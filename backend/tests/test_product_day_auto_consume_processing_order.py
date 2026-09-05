from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    compute_product_day_auto_deduction,
)


def _connection():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    conn = engine.connect()
    conn.execute(
        text(
            """
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT,
                event_type TEXT NOT NULL,
                quantity NUMERIC NOT NULL,
                old_quantity NUMERIC,
                new_quantity NUMERIC,
                source TEXT NOT NULL,
                purchase_date TEXT,
                effective_at TEXT,
                event_priority INTEGER,
                source_reference TEXT,
                source_line_id TEXT
            )
            """
        )
    )
    return engine, conn


def _event(conn, event_id: str, event_type: str, quantity: int, old: int, new: int, effective_at: str):
    source = "store_import" if event_type == "purchase" else "auto_repurchase"
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, household_article_id, event_type, quantity,
                old_quantity, new_quantity, source, purchase_date, effective_at,
                event_priority, source_reference, source_line_id
            ) VALUES (
                :id, 'h1', 'a1', :event_type, :quantity,
                :old_quantity, :new_quantity, :source, '2026-08-26', :effective_at,
                10, :source_reference, :source_line_id
            )
            """
        ),
        {
            "id": event_id,
            "event_type": event_type,
            "quantity": quantity,
            "old_quantity": old,
            "new_quantity": new,
            "source": source,
            "effective_at": effective_at,
            "source_reference": f"receipt:{event_id}",
            "source_line_id": f"line:{event_id}",
        },
    )


def _decision(conn, mode: str, pre: int, purchased: int):
    return compute_product_day_auto_deduction(
        conn,
        household_id="h1",
        household_article_id="a1",
        purchase_date="2026-08-26T09:00:00+02:00",
        mode=mode,
        pre_purchase_total=pre,
        purchased_quantity=purchased,
    )


def test_backdated_same_day_purchase_still_extends_one_cumulative_purchase_group():
    engine, conn = _connection()
    try:
        # The 14:00 receipt happened to be processed first: 10 + 3 - 3 = 10.
        _event(conn, "p-late", "purchase", 3, 10, 13, "2026-08-26T14:00:00+02:00")
        _event(conn, "c-late", "auto_repurchase", -3, 13, 10, "2026-08-26T14:00:00+02:00")

        # A 09:00 receipt is processed afterwards. It must extend the same
        # product-day from 3 to 5 purchased units, not start a second purchase.
        result = _decision(conn, AUTO_CONSUME_PURCHASED_QUANTITY, pre=10, purchased=2)
        assert result["purchase_day"] == "2026-08-26"
        assert result["day_start_stock"] == 10
        assert result["prior_day_purchased_quantity"] == 3
        assert result["prior_day_auto_consumed_quantity"] == 3
        assert result["cumulative_day_purchased_quantity"] == 5
        assert result["requested_deduction_quantity"] == 2
    finally:
        conn.close()
        engine.dispose()


def test_backdated_same_day_purchase_does_not_repeat_all_existing_consumption():
    engine, conn = _connection()
    try:
        # A later receipt consumed the five units that existed before this
        # product-day. The later-processed earlier receipt must not consume them
        # a second time.
        _event(conn, "p-late", "purchase", 2, 5, 7, "2026-08-26T14:00:00+02:00")
        _event(conn, "c-late", "auto_repurchase", -5, 7, 2, "2026-08-26T14:00:00+02:00")

        result = _decision(conn, AUTO_CONSUME_ALL_EXISTING, pre=2, purchased=3)
        assert result["day_start_stock"] == 5
        assert result["cumulative_day_purchased_quantity"] == 5
        assert result["requested_deduction_quantity"] == 0
    finally:
        conn.close()
        engine.dispose()
