from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_NONE,
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
                source_line_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    return engine, conn


def _event(
    conn,
    *,
    event_id: str,
    household: str = "h1",
    article: str = "a1",
    event_type: str,
    quantity: int,
    old_quantity: int,
    new_quantity: int,
    source: str,
    purchase_date: str,
    effective_at: str,
):
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, household_article_id, event_type, quantity,
                old_quantity, new_quantity, source, purchase_date, effective_at,
                event_priority, source_reference, source_line_id
            ) VALUES (
                :id, :household_id, :household_article_id, :event_type, :quantity,
                :old_quantity, :new_quantity, :source, :purchase_date, :effective_at,
                10, :source_reference, :source_line_id
            )
            """
        ),
        {
            "id": event_id,
            "household_id": household,
            "household_article_id": article,
            "event_type": event_type,
            "quantity": quantity,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "source": source,
            "purchase_date": purchase_date,
            "effective_at": effective_at,
            "source_reference": f"receipt:{event_id}",
            "source_line_id": f"line:{event_id}",
        },
    )


def _decision(conn, *, mode: str, pre: int, purchased: int, purchase_date: str = "2026-08-26", article: str = "a1", household: str = "h1"):
    return compute_product_day_auto_deduction(
        conn,
        household_id=household,
        household_article_id=article,
        purchase_date=purchase_date,
        mode=mode,
        pre_purchase_total=pre,
        purchased_quantity=purchased,
    )


def test_first_purchase_of_day_keeps_existing_purchased_quantity_semantics():
    engine, conn = _connection()
    try:
        result = _decision(conn, mode=AUTO_CONSUME_PURCHASED_QUANTITY, pre=10, purchased=2)
        assert result["product_day_applied"] is True
        assert result["day_start_stock"] == 10
        assert result["cumulative_day_purchased_quantity"] == 2
        assert result["requested_deduction_quantity"] == 2
    finally:
        conn.close()
        engine.dispose()


def test_second_same_day_purchase_is_cumulative_for_purchased_quantity_mode():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="p1",
            event_type="purchase",
            quantity=2,
            old_quantity=10,
            new_quantity=12,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T09:00:00",
        )
        _event(
            conn,
            event_id="c1",
            event_type="auto_repurchase",
            quantity=-2,
            old_quantity=12,
            new_quantity=10,
            source="auto_repurchase",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T09:00:00",
        )

        result = _decision(conn, mode=AUTO_CONSUME_PURCHASED_QUANTITY, pre=10, purchased=3)
        assert result["day_start_stock"] == 10
        assert result["prior_day_purchased_quantity"] == 2
        assert result["prior_day_auto_consumed_quantity"] == 2
        assert result["cumulative_day_purchased_quantity"] == 5
        assert result["requested_deduction_quantity"] == 3
    finally:
        conn.close()
        engine.dispose()


def test_same_day_purchased_quantity_stops_consuming_after_old_stock_is_exhausted():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="p1",
            event_type="purchase",
            quantity=3,
            old_quantity=4,
            new_quantity=7,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T09:00:00",
        )
        _event(
            conn,
            event_id="c1",
            event_type="auto_repurchase",
            quantity=-3,
            old_quantity=7,
            new_quantity=4,
            source="auto_repurchase",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T09:00:00",
        )

        second = _decision(conn, mode=AUTO_CONSUME_PURCHASED_QUANTITY, pre=4, purchased=3)
        assert second["requested_deduction_quantity"] == 1

        _event(
            conn,
            event_id="p2",
            event_type="purchase",
            quantity=3,
            old_quantity=4,
            new_quantity=7,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T14:00:00",
        )
        _event(
            conn,
            event_id="c2",
            event_type="auto_repurchase",
            quantity=-1,
            old_quantity=7,
            new_quantity=6,
            source="auto_repurchase",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T14:00:00",
        )

        third = _decision(conn, mode=AUTO_CONSUME_PURCHASED_QUANTITY, pre=6, purchased=2)
        assert third["prior_day_purchased_quantity"] == 6
        assert third["prior_day_auto_consumed_quantity"] == 4
        assert third["requested_deduction_quantity"] == 0
    finally:
        conn.close()
        engine.dispose()


def test_all_existing_is_consumed_only_once_per_product_day():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="p1",
            event_type="purchase",
            quantity=2,
            old_quantity=5,
            new_quantity=7,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T08:00:00",
        )
        _event(
            conn,
            event_id="c1",
            event_type="auto_repurchase",
            quantity=-5,
            old_quantity=7,
            new_quantity=2,
            source="auto_repurchase",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T08:00:00",
        )

        result = _decision(conn, mode=AUTO_CONSUME_ALL_EXISTING, pre=2, purchased=3)
        assert result["day_start_stock"] == 5
        assert result["cumulative_day_purchased_quantity"] == 5
        assert result["requested_deduction_quantity"] == 0
    finally:
        conn.close()
        engine.dispose()


def test_different_purchase_day_starts_a_new_group():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="p-old",
            event_type="purchase",
            quantity=4,
            old_quantity=8,
            new_quantity=12,
            source="store_import",
            purchase_date="2026-08-25",
            effective_at="2026-08-25T12:00:00",
        )
        _event(
            conn,
            event_id="c-old",
            event_type="auto_repurchase",
            quantity=-4,
            old_quantity=12,
            new_quantity=8,
            source="auto_repurchase",
            purchase_date="2026-08-25",
            effective_at="2026-08-25T12:00:00",
        )

        result = _decision(conn, mode=AUTO_CONSUME_PURCHASED_QUANTITY, pre=8, purchased=2, purchase_date="2026-08-26")
        assert result["prior_day_purchased_quantity"] == 0
        assert result["prior_day_auto_consumed_quantity"] == 0
        assert result["day_start_stock"] == 8
        assert result["requested_deduction_quantity"] == 2
    finally:
        conn.close()
        engine.dispose()


def test_other_households_and_articles_do_not_join_product_day():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="other-article",
            article="a2",
            event_type="purchase",
            quantity=9,
            old_quantity=20,
            new_quantity=29,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T07:00:00",
        )
        _event(
            conn,
            event_id="other-household",
            household="h2",
            event_type="purchase",
            quantity=7,
            old_quantity=30,
            new_quantity=37,
            source="store_import",
            purchase_date="2026-08-26",
            effective_at="2026-08-26T07:30:00",
        )

        result = _decision(conn, mode=AUTO_CONSUME_ALL_EXISTING, pre=6, purchased=2)
        assert result["prior_day_purchased_quantity"] == 0
        assert result["day_start_stock"] == 6
        assert result["requested_deduction_quantity"] == 6
    finally:
        conn.close()
        engine.dispose()


def test_iso_timestamp_uses_receipt_calendar_day():
    engine, conn = _connection()
    try:
        _event(
            conn,
            event_id="p1",
            event_type="purchase",
            quantity=2,
            old_quantity=5,
            new_quantity=7,
            source="store_import",
            purchase_date="2026-08-26T09:00:00+02:00",
            effective_at="2026-08-26T09:00:00+02:00",
        )
        _event(
            conn,
            event_id="c1",
            event_type="auto_repurchase",
            quantity=-2,
            old_quantity=7,
            new_quantity=5,
            source="auto_repurchase",
            purchase_date="2026-08-26T09:00:00+02:00",
            effective_at="2026-08-26T09:00:00+02:00",
        )

        result = _decision(
            conn,
            mode=AUTO_CONSUME_PURCHASED_QUANTITY,
            pre=5,
            purchased=1,
            purchase_date="2026-08-26T21:15:00+02:00",
        )
        assert result["purchase_day"] == "2026-08-26"
        assert result["prior_day_purchased_quantity"] == 2
        assert result["requested_deduction_quantity"] == 1
    finally:
        conn.close()
        engine.dispose()


def test_unknown_purchase_date_falls_back_to_legacy_per_purchase_behavior():
    engine, conn = _connection()
    try:
        result = _decision(conn, mode=AUTO_CONSUME_ALL_EXISTING, pre=5, purchased=2, purchase_date="26-08-2026")
        assert result["product_day_applied"] is False
        assert result["requested_deduction_quantity"] == 5
    finally:
        conn.close()
        engine.dispose()


def test_none_mode_never_requests_auto_consumption():
    engine, conn = _connection()
    try:
        result = _decision(conn, mode=AUTO_CONSUME_NONE, pre=9, purchased=4)
        assert result["requested_deduction_quantity"] == 0
    finally:
        conn.close()
        engine.dispose()
