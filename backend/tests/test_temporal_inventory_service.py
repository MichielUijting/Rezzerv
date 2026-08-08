from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, text

from app.services.temporal_inventory_service import (
    TemporalInventoryEvent,
    ensure_temporal_inventory_schema,
    insert_temporal_event,
    ordered_events,
    replay_article,
)


def _connection():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    conn = engine.connect()
    conn.execute(text(
        """
        CREATE TABLE inventory_events (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            article_id TEXT,
            household_article_id TEXT,
            article_name TEXT NOT NULL,
            location_id TEXT,
            location_label TEXT,
            event_type TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            old_quantity NUMERIC,
            new_quantity NUMERIC,
            source TEXT NOT NULL,
            note TEXT,
            purchase_date TEXT,
            supplier_name TEXT,
            article_number TEXT,
            price NUMERIC,
            currency TEXT,
            barcode TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    return conn


def _event(moment: str, quantity: str, *, event_type: str = "purchase", ref: str):
    return TemporalInventoryEvent(
        household_id="H1",
        household_article_id="A1",
        article_name="Melk",
        event_type=event_type,
        quantity=Decimal(quantity),
        effective_at=moment,
        source="test",
        source_reference=ref,
    )


def _scenario(import_order):
    conn = _connection()
    ensure_temporal_inventory_schema(conn)
    events = {
        "A": _event("2026-08-01T10:00:00+00:00", "3", ref="A"),
        "B": _event("2026-08-03T10:00:00+00:00", "2", ref="B"),
        "C": _event("2026-08-04T10:00:00+00:00", "1", event_type="consume", ref="C"),
        "D": _event("2026-08-06T10:00:00+00:00", "4", ref="D"),
    }
    for key in import_order:
        insert_temporal_event(conn, events[key])
    report = replay_article(conn, household_id="H1", household_article_id="A1")
    rows = ordered_events(conn, household_id="H1", household_article_id="A1")
    balances = conn.execute(text(
        """
        SELECT source_reference, old_quantity, new_quantity
        FROM inventory_events
        WHERE household_id='H1'
        ORDER BY datetime(effective_at), event_priority, source_reference, id
        """
    )).mappings().all()
    return report, [row["source_reference"] for row in rows], [
        (row["source_reference"], Decimal(str(row["old_quantity"])), Decimal(str(row["new_quantity"])))
        for row in balances
    ]


def test_import_order_does_not_change_inventory_history_or_result():
    chronological = _scenario(["A", "B", "C", "D"])
    reverse = _scenario(["D", "C", "B", "A"])
    mixed = _scenario(["C", "A", "D", "B"])

    for result in (chronological, reverse, mixed):
        report, order, balances = result
        assert order == ["A", "B", "C", "D"]
        assert report["current_quantity"] == Decimal("8")
        assert balances == [
            ("A", Decimal("0"), Decimal("3")),
            ("B", Decimal("3"), Decimal("5")),
            ("C", Decimal("5"), Decimal("4")),
            ("D", Decimal("4"), Decimal("8")),
        ]


def test_late_receipt_is_inserted_before_later_consumption():
    conn = _connection()
    ensure_temporal_inventory_schema(conn)

    insert_temporal_event(conn, _event("2026-08-06T12:00:00+00:00", "2", ref="newer-receipt"))
    insert_temporal_event(conn, _event("2026-08-07T08:00:00+00:00", "1", event_type="consume", ref="consumption"))
    first = replay_article(conn, household_id="H1", household_article_id="A1")
    assert first["current_quantity"] == Decimal("1")

    insert_temporal_event(conn, _event("2026-08-04T18:00:00+00:00", "3", ref="late-old-receipt"))
    second = replay_article(conn, household_id="H1", household_article_id="A1")
    assert second["current_quantity"] == Decimal("4")

    rows = conn.execute(text(
        """
        SELECT source_reference, old_quantity, new_quantity
        FROM inventory_events
        ORDER BY datetime(effective_at), event_priority, source_reference, id
        """
    )).mappings().all()
    assert [(row["source_reference"], int(row["old_quantity"]), int(row["new_quantity"])) for row in rows] == [
        ("late-old-receipt", 0, 3),
        ("newer-receipt", 3, 5),
        ("consumption", 5, 4),
    ]


def test_existing_purchase_date_is_backfilled_as_effective_time():
    conn = _connection()
    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, source, purchase_date, created_at
        ) VALUES (
            'legacy', 'H1', 'A1', 'A1', 'Melk', 'purchase', 2,
            'legacy', '2026-08-02', '2026-08-08 12:00:00'
        )
        """
    ))
    ensure_temporal_inventory_schema(conn)
    row = conn.execute(text(
        "SELECT effective_at, recorded_at, effective_at_precision, event_priority FROM inventory_events WHERE id='legacy'"
    )).mappings().one()
    assert str(row["effective_at"]).startswith("2026-08-02T00:00:00")
    assert str(row["recorded_at"]).startswith("2026-08-08")
    assert row["effective_at_precision"] == "date"
    assert int(row["event_priority"]) == 10
