from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.receipt_inventory_lifecycle_service import (
    remove_receipt_inventory_events,
    retime_receipt_inventory_events,
)
from app.services.temporal_inventory_service import ensure_temporal_inventory_schema, replay_inventory_events


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                household_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                old_quantity NUMERIC NOT NULL,
                new_quantity NUMERIC NOT NULL,
                purchase_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_location_quantities (
                household_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                quantity NUMERIC NOT NULL,
                updated_at TEXT,
                PRIMARY KEY (household_id, article_id, location_id)
            )
        """))
        ensure_temporal_inventory_schema(conn)
    return engine


def _event(conn, *, household="h1", article="a1", event_type="purchase", old=0, new=1, effective_at, source_reference=None, line=None):
    conn.execute(text("""
        INSERT INTO inventory_events (
            household_id, article_id, event_type, old_quantity, new_quantity,
            purchase_date, effective_at, recorded_at, effective_at_precision,
            event_priority, source_reference, source_line_id
        ) VALUES (
            :household, :article, :event_type, :old, :new,
            substr(:effective_at, 1, 10), :effective_at, CURRENT_TIMESTAMP,
            'datetime', 20, :source_reference, :line
        )
    """), {
        "household": household,
        "article": article,
        "event_type": event_type,
        "old": old,
        "new": new,
        "effective_at": effective_at,
        "source_reference": source_reference,
        "line": line,
    })


def test_delete_old_unpacked_receipt_removes_effect_and_replays_projection():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO inventory_location_quantities VALUES ('h1','a1','pantry',4,NULL)"))
        _event(conn, effective_at="2026-08-04T18:21:37", old=0, new=3, source_reference="receipt:r-old", line="0")
        _event(conn, effective_at="2026-08-06T12:00:00", old=3, new=5, source_reference="receipt:r-new", line="0")
        _event(conn, event_type="consumption", effective_at="2026-08-07T08:00:00", old=5, new=4)
        replay_inventory_events(conn, household_id="h1", article_id="a1")

        result = remove_receipt_inventory_events(conn, receipt_table_id="r-old", household_id="h1")

        assert result["removed_event_count"] == 1
        remaining = conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE source_reference='receipt:r-old'" )).scalar_one()
        assert remaining == 0
        replay = replay_inventory_events(conn, household_id="h1", article_id="a1")
        assert float(replay["final_quantity"]) == 1.0
        projection = conn.execute(text("SELECT quantity FROM inventory_location_quantities WHERE household_id='h1' AND article_id='a1'" )).scalar_one()
        assert float(projection) == 1.0


def test_correct_receipt_timestamp_reorders_existing_event_without_changing_total_stock():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO inventory_location_quantities VALUES ('h1','a1','pantry',4,NULL)"))
        _event(conn, effective_at="2026-08-08T09:00:00", old=1, new=4, source_reference="receipt:r1", line="0")
        _event(conn, event_type="consumption", effective_at="2026-08-07T08:00:00", old=0, new=-1)
        replay_inventory_events(conn, household_id="h1", article_id="a1")

        result = retime_receipt_inventory_events(
            conn,
            receipt_table_id="r1",
            household_id="h1",
            purchase_at="2026-08-04T18:21:37",
        )

        assert result["updated_event_count"] == 1
        rows = conn.execute(text("SELECT effective_at, old_quantity, new_quantity FROM inventory_events ORDER BY effective_at, id" )).mappings().all()
        assert rows[0]["effective_at"] == "2026-08-04T18:21:37"
        assert float(rows[0]["old_quantity"]) == 0.0
        assert float(rows[0]["new_quantity"]) == 3.0
        assert float(rows[1]["old_quantity"]) == 3.0
        assert float(rows[1]["new_quantity"]) == 2.0
        projection = conn.execute(text("SELECT quantity FROM inventory_location_quantities WHERE household_id='h1' AND article_id='a1'" )).scalar_one()
        assert float(projection) == 2.0


def test_lifecycle_is_household_scoped_for_same_receipt_reference():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO inventory_location_quantities VALUES ('h1','a1','pantry',2,NULL)"))
        conn.execute(text("INSERT INTO inventory_location_quantities VALUES ('h2','a1','pantry',7,NULL)"))
        _event(conn, household="h1", effective_at="2026-08-04T10:00:00", old=0, new=2, source_reference="receipt:r1")
        _event(conn, household="h2", effective_at="2026-08-04T10:00:00", old=0, new=7, source_reference="receipt:r1")
        replay_inventory_events(conn, household_id="h1", article_id="a1")
        replay_inventory_events(conn, household_id="h2", article_id="a1")

        remove_receipt_inventory_events(conn, receipt_table_id="r1", household_id="h1")

        h1_count = conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE household_id='h1'" )).scalar_one()
        h2_count = conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE household_id='h2'" )).scalar_one()
        assert h1_count == 0
        assert h2_count == 1
