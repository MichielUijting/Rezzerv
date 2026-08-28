from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.services.canonical_inventory_identity_service import apply_inventory_purchase_by_identity
from app.services.temporal_inventory_service import (
    TemporalInventoryEvent,
    ensure_temporal_inventory_schema,
    insert_temporal_event,
    ordered_events,
    reconcile_inventory_total,
    replay_article,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260828_03_inventory_temporal_schema_authority.py"
)


def _upgrade_temporal_schema(conn) -> None:
    spec = importlib.util.spec_from_file_location("inventory_temporal_authority", MIGRATION_PATH)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        migration.upgrade()


def _connection(*, migrate: bool = True):
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
    conn.execute(text(
        """
        CREATE TABLE inventory (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            aantal INTEGER NOT NULL,
            household_id TEXT NOT NULL,
            household_article_id TEXT,
            space_id TEXT,
            sublocation_id TEXT,
            status TEXT DEFAULT 'active',
            updated_at TEXT
        )
        """
    ))
    conn.execute(text(
        """
        CREATE UNIQUE INDEX uq_inventory_active_locationless_household_article
        ON inventory (household_id, household_article_id)
        WHERE COALESCE(status, 'active') = 'active'
          AND household_article_id IS NOT NULL
          AND space_id IS NULL
          AND sublocation_id IS NULL
        """
    ))
    if migrate:
        _upgrade_temporal_schema(conn)
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


def test_existing_purchase_date_is_backfilled_by_alembic_as_effective_time():
    conn = _connection(migrate=False)
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
    _upgrade_temporal_schema(conn)
    row = conn.execute(text(
        "SELECT effective_at, recorded_at, effective_at_precision, event_priority FROM inventory_events WHERE id='legacy'"
    )).mappings().one()
    assert str(row["effective_at"]).startswith("2026-08-02T00:00:00")
    assert str(row["recorded_at"]).startswith("2026-08-08")
    assert row["effective_at_precision"] == "date"
    assert int(row["event_priority"]) == 10


def test_legacy_dutch_date_is_normalized_by_alembic_for_temporal_ordering():
    conn = _connection(migrate=False)
    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, source, purchase_date, created_at
        ) VALUES (
            'legacy-nl', 'H1', 'A1', 'A1', 'Melk', 'purchase', 2,
            'legacy', '02-08-2026', '2026-08-08 12:00:00'
        )
        """
    ))
    _upgrade_temporal_schema(conn)
    row = conn.execute(text(
        "SELECT effective_at, effective_at_precision FROM inventory_events WHERE id='legacy-nl'"
    )).mappings().one()
    assert str(row["effective_at"]).startswith("2026-08-02T00:00:00")
    assert row["effective_at_precision"] == "date"


def test_runtime_temporal_guard_is_validation_only_and_does_not_mutate_legacy_schema():
    conn = _connection(migrate=False)
    before = tuple(conn.execute(text(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    )).all())
    with pytest.raises(RuntimeError, match="niet gemigreerd"):
        ensure_temporal_inventory_schema(conn)
    after = tuple(conn.execute(text(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    )).all())
    assert after == before


def _create_projection_tables(conn):
    conn.execute(text(
        """
        CREATE TABLE household_articles (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            naam TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
        """
    ))
    conn.execute(text("INSERT INTO household_articles (id, household_id, naam) VALUES ('A1','H1','Melk')"))


def test_canonical_purchase_flow_reconciles_visible_stock_after_late_receipt():
    conn = _connection()
    _create_projection_tables(conn)
    conn.execute(text(
        "INSERT INTO inventory (id, naam, aantal, household_id, household_article_id, space_id, status) "
        "VALUES ('I1','Melk',1,'H1','A1','S1','active')"
    ))

    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, source, purchase_date, created_at,
            effective_at, recorded_at, effective_at_precision, event_priority
        ) VALUES
            ('newer', 'H1', 'A1', 'A1', 'Melk', 'purchase', 2, 'receipt', '06-08-2026', '2026-08-06 12:00:00',
             '2026-08-06T00:00:00+00:00', '2026-08-06T12:00:00+00:00', 'date', 10),
            ('consume', 'H1', 'A1', 'A1', 'Melk', 'consume', 1, 'usage', NULL, '2026-08-07 08:00:00',
             '2026-08-07T08:00:00+00:00', '2026-08-07T08:00:00+00:00', 'datetime', 40)
        """
    ))

    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, source, purchase_date, created_at,
            effective_at, recorded_at, effective_at_precision, event_priority
        ) VALUES (
            'late-old', 'H1', 'A1', 'A1', 'Melk', 'purchase', 3,
            'receipt', '04-08-2026', '2026-08-08 09:00:00',
            '2026-08-04T00:00:00+00:00', '2026-08-08T09:00:00+00:00', 'date', 10
        )
        """
    ))
    inventory_id = apply_inventory_purchase_by_identity(
        conn,
        household_id='H1',
        household_article_id='A1',
        quantity=3,
        space_id='S1',
        sublocation_id=None,
    )
    assert inventory_id == 'I1'

    visible_total = conn.execute(text(
        "SELECT SUM(aantal) FROM inventory WHERE household_id='H1' AND household_article_id='A1'"
    )).scalar()
    assert int(visible_total) == 4

    rows = conn.execute(text(
        """
        SELECT id, old_quantity, new_quantity
        FROM inventory_events
        WHERE household_id='H1'
        ORDER BY datetime(effective_at), event_priority, id
        """
    )).mappings().all()
    assert [(row['id'], int(row['old_quantity']), int(row['new_quantity'])) for row in rows] == [
        ('late-old', 0, 3),
        ('newer', 3, 5),
        ('consume', 5, 4),
    ]


def test_reconcile_repairs_projection_even_when_import_side_effect_was_wrong():
    conn = _connection()
    conn.execute(text(
        "INSERT INTO inventory (id, naam, aantal, household_id, household_article_id, space_id, status) "
        "VALUES ('I1','Melk',99,'H1','A1','S1','active')"
    ))
    ensure_temporal_inventory_schema(conn)
    insert_temporal_event(conn, _event("2026-08-01T10:00:00+00:00", "3", ref="A"))
    insert_temporal_event(conn, _event("2026-08-03T10:00:00+00:00", "1", event_type="consume", ref="B"))

    report = reconcile_inventory_total(
        conn,
        household_id='H1',
        household_article_id='A1',
        preferred_inventory_id='I1',
    )
    assert report['current_quantity'] == Decimal('2')
    assert int(conn.execute(text("SELECT aantal FROM inventory WHERE id='I1'")).scalar()) == 2


def test_unpacking_uses_exact_receipt_purchase_time_not_batch_date_label():
    conn = _connection()
    _create_projection_tables(conn)
    conn.execute(text(
        "INSERT INTO inventory (id, naam, aantal, household_id, household_article_id, space_id, status) "
        "VALUES ('I1','Melk',0,'H1','A1','S1','active')"
    ))
    conn.execute(text(
        """
        CREATE TABLE receipt_tables (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            purchase_at TEXT,
            purchase_at_source TEXT
        )
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE purchase_import_batches (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            source_type TEXT,
            source_reference TEXT,
            created_at TEXT
        )
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE purchase_import_lines (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            matched_household_article_id TEXT,
            target_location_id TEXT,
            quantity_raw NUMERIC,
            processing_status TEXT,
            ui_sort_order INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """
    ))
    conn.execute(text(
        "INSERT INTO receipt_tables (id, household_id, purchase_at, purchase_at_source) "
        "VALUES ('R1','H1','2026-08-04T18:21:37','detected')"
    ))
    conn.execute(text(
        "INSERT INTO purchase_import_batches (id, household_id, source_type, source_reference, created_at) "
        "VALUES ('B1','H1','receipt','receipt:R1','2026-08-08 09:00:00')"
    ))
    conn.execute(text(
        """
        INSERT INTO purchase_import_lines (
            id, batch_id, matched_household_article_id, target_location_id,
            quantity_raw, processing_status, ui_sort_order, created_at, updated_at
        ) VALUES (
            'L1','B1','A1','S1',3,'pending',0,'2026-08-08 09:00:00','2026-08-08 09:00:00'
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name, location_id,
            event_type, quantity, source, purchase_date, created_at,
            effective_at, recorded_at, effective_at_precision, event_priority
        ) VALUES (
            'E1','H1','A1','A1','Melk','S1','purchase',3,'store_import','2026-08-04','2026-08-08 09:00:01',
            '2026-08-04T00:00:00+00:00','2026-08-08T09:00:01+00:00','date',10
        )
        """
    ))

    apply_inventory_purchase_by_identity(
        conn,
        household_id='H1',
        household_article_id='A1',
        quantity=3,
        space_id='S1',
        sublocation_id=None,
    )

    event = conn.execute(text(
        """
        SELECT effective_at, effective_at_precision, source_reference, source_line_id,
               old_quantity, new_quantity
        FROM inventory_events WHERE id='E1'
        """
    )).mappings().one()
    assert str(event['effective_at']).startswith('2026-08-04T18:21:37')
    assert event['effective_at_precision'] == 'datetime'
    assert event['source_reference'] == 'receipt:R1'
    assert event['source_line_id'] == 'L1'
    assert int(event['old_quantity']) == 0
    assert int(event['new_quantity']) == 3
