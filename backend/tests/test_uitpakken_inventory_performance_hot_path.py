from sqlalchemy import create_engine, text

import app.services.canonical_inventory_identity_service as inventory_identity_service
from app.services.canonical_inventory_identity_service import (
    ensure_locationless_inventory_identity_guard,
)
from app.services.temporal_inventory_service import (
    ensure_temporal_inventory_schema,
    replay_article,
)


def _create_inventory_events_schema(conn):
    conn.execute(text(
        """
        CREATE TABLE inventory_events (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            article_id TEXT,
            household_article_id TEXT,
            article_name TEXT,
            location_id TEXT,
            location_label TEXT,
            event_type TEXT,
            quantity NUMERIC,
            old_quantity NUMERIC,
            new_quantity NUMERIC,
            source TEXT,
            note TEXT,
            purchase_date TEXT,
            supplier_name TEXT,
            article_number TEXT,
            price NUMERIC,
            currency TEXT,
            barcode TEXT,
            created_at TEXT,
            effective_at TEXT,
            recorded_at TEXT,
            effective_at_precision TEXT NOT NULL DEFAULT 'datetime',
            event_priority INTEGER NOT NULL DEFAULT 100,
            source_reference TEXT,
            source_line_id TEXT,
            replayed_at TEXT
        )
        """
    ))


def _create_receipt_purchase_fast_path_schema(conn):
    conn.execute(text(
        """
        CREATE TABLE household_articles (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            naam TEXT,
            status TEXT
        )
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE inventory (
            id TEXT PRIMARY KEY,
            naam TEXT,
            aantal NUMERIC,
            household_id TEXT,
            household_article_id TEXT,
            space_id TEXT,
            sublocation_id TEXT,
            status TEXT,
            updated_at TEXT
        )
        """
    ))
    _create_inventory_events_schema(conn)
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
            updated_at TEXT,
            created_at TEXT,
            ui_sort_order INTEGER
        )
        """
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


def _seed_receipt_purchase_case(conn, *, existing_effective_at: str, new_purchase_at: str):
    conn.execute(text(
        "INSERT INTO household_articles (id, household_id, naam, status) "
        "VALUES ('article-1', 'hh-1', 'Melk', 'active')"
    ))
    conn.execute(text(
        """
        INSERT INTO inventory (
            id, naam, aantal, household_id, household_article_id,
            space_id, sublocation_id, status, updated_at
        ) VALUES (
            'inventory-1', 'Melk', 2, 'hh-1', 'article-1',
            NULL, NULL, 'active', '2026-08-26T09:00:00+00:00'
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, old_quantity, new_quantity, source,
            created_at, effective_at, recorded_at, effective_at_precision,
            event_priority, source_reference, source_line_id
        ) VALUES (
            'event-existing', 'hh-1', 'article-1', 'article-1', 'Melk',
            'purchase', 2, 0, 2, 'store_import',
            :existing_effective_at, :existing_effective_at, :existing_effective_at,
            'datetime', 10, 'receipt:existing', 'line-existing'
        )
        """
    ), {"existing_effective_at": existing_effective_at})
    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            event_type, quantity, old_quantity, new_quantity, source,
            purchase_date, created_at, effective_at, recorded_at,
            effective_at_precision, event_priority, source_reference, source_line_id
        ) VALUES (
            'event-new', 'hh-1', 'article-1', 'article-1', 'Melk',
            'purchase', 1, 2, 3, 'store_import',
            '2026-08-26', '2026-08-26T10:00:00+00:00', NULL, NULL,
            'datetime', 100, NULL, NULL
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO purchase_import_batches (
            id, household_id, source_type, source_reference, created_at
        ) VALUES (
            'batch-1', 'hh-1', 'receipt', 'receipt:receipt-new',
            '2026-08-26T10:00:00+00:00'
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO purchase_import_lines (
            id, batch_id, matched_household_article_id, target_location_id,
            quantity_raw, processing_status, updated_at, created_at, ui_sort_order
        ) VALUES (
            'line-new', 'batch-1', 'article-1', NULL,
            1, 'pending', '2026-08-26T10:00:00+00:00',
            '2026-08-26T10:00:00+00:00', 1
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO receipt_tables (id, household_id, purchase_at, purchase_at_source)
        VALUES ('receipt-new', 'hh-1', :purchase_at, 'detected')
        """
    ), {"purchase_at": new_purchase_at})


def test_temporal_schema_ensure_is_write_free_when_rows_are_current():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _create_inventory_events_schema(conn)
        conn.execute(text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, household_article_id, article_name,
                event_type, quantity, old_quantity, new_quantity, source,
                purchase_date, created_at, effective_at, recorded_at,
                effective_at_precision, event_priority, replayed_at
            ) VALUES (
                'event-1', 'hh-1', 'article-1', 'article-1', 'Melk',
                'purchase', 1, 0, 1, 'store_import',
                '2026-08-25', '2026-08-25T10:00:00+00:00',
                '2026-08-25T00:00:00+00:00', '2026-08-25T10:00:00+00:00',
                'date', 10, '2026-08-25T10:00:01+00:00'
            )
            """
        ))
        ensure_temporal_inventory_schema(conn)
        before = conn.execute(text("SELECT total_changes()" )).scalar_one()
        ensure_temporal_inventory_schema(conn)
        after = conn.execute(text("SELECT total_changes()" )).scalar_one()

    assert after == before


def test_replay_does_not_rewrite_unchanged_historical_balances():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _create_inventory_events_schema(conn)
        conn.execute(text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, household_article_id, article_name,
                event_type, quantity, old_quantity, new_quantity, source,
                created_at, effective_at, recorded_at, effective_at_precision,
                event_priority, source_reference, source_line_id, replayed_at
            ) VALUES
                (
                    'event-1', 'hh-1', 'article-1', 'article-1', 'Melk',
                    'purchase', 2, 0, 2, 'store_import',
                    '2026-08-24T10:00:00+00:00', '2026-08-24T10:00:00+00:00',
                    '2026-08-24T10:00:00+00:00', 'datetime', 10,
                    'receipt:1', 'line-1', '2026-08-24T10:00:01+00:00'
                ),
                (
                    'event-2', 'hh-1', 'article-1', 'article-1', 'Melk',
                    'consume', 1, 2, 1, 'manual',
                    '2026-08-25T10:00:00+00:00', '2026-08-25T10:00:00+00:00',
                    '2026-08-25T10:00:00+00:00', 'datetime', 40,
                    NULL, NULL, '2026-08-25T10:00:01+00:00'
                )
            """
        ))
        ensure_temporal_inventory_schema(conn)
        before = conn.execute(text("SELECT total_changes()" )).scalar_one()
        replay = replay_article(conn, household_id="hh-1", household_article_id="article-1")
        after = conn.execute(text("SELECT total_changes()" )).scalar_one()

    assert replay["current_quantity"] == 1
    assert after == before


def test_locationless_identity_guard_skips_duplicate_scan_after_index_exists():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                household_article_id TEXT,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT
            )
            """
        ))
        ensure_locationless_inventory_identity_guard(conn)

        statements = []
        raw_connection = conn.connection.driver_connection
        raw_connection.set_trace_callback(statements.append)
        try:
            ensure_locationless_inventory_identity_guard(conn)
        finally:
            raw_connection.set_trace_callback(None)

    normalized = "\n".join(statements).lower()
    assert "group by household_id, household_article_id" not in normalized
    assert "pragma table_info(inventory)" not in normalized


def test_current_receipt_purchase_uses_append_fast_path_without_global_ensure_or_replay(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _create_receipt_purchase_fast_path_schema(conn)
        _seed_receipt_purchase_case(
            conn,
            existing_effective_at="2026-08-25T10:00:00+00:00",
            new_purchase_at="2026-08-26T10:00:00+00:00",
        )

        monkeypatch.setattr(
            inventory_identity_service,
            "ensure_temporal_inventory_schema",
            lambda _conn: (_ for _ in ()).throw(AssertionError("global temporal ensure must not run")),
        )
        monkeypatch.setattr(
            inventory_identity_service,
            "reconcile_inventory_total",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full replay must not run")),
        )

        inventory_id = inventory_identity_service.apply_inventory_purchase_by_identity(
            conn,
            household_id="hh-1",
            household_article_id="article-1",
            quantity=1,
            space_id=None,
            sublocation_id=None,
        )

        inventory_total = conn.execute(text(
            "SELECT SUM(aantal) FROM inventory WHERE household_id='hh-1' AND household_article_id='article-1'"
        )).scalar_one()
        hydrated = conn.execute(text(
            """
            SELECT effective_at, recorded_at, event_priority, source_reference, source_line_id
            FROM inventory_events WHERE id='event-new'
            """
        )).mappings().one()

    assert inventory_id == "inventory-1"
    assert int(inventory_total) == 3
    assert hydrated["effective_at"] == "2026-08-26T10:00:00+00:00"
    assert hydrated["recorded_at"] == "2026-08-26T10:00:00+00:00"
    assert hydrated["event_priority"] == 10
    assert hydrated["source_reference"] == "receipt:receipt-new"
    assert hydrated["source_line_id"] == "line-new"


def test_backdated_receipt_purchase_falls_back_to_full_reconcile(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    reconcile_calls = []
    with engine.begin() as conn:
        _create_receipt_purchase_fast_path_schema(conn)
        _seed_receipt_purchase_case(
            conn,
            existing_effective_at="2026-08-26T12:00:00+00:00",
            new_purchase_at="2026-08-24T10:00:00+00:00",
        )

        monkeypatch.setattr(
            inventory_identity_service,
            "ensure_temporal_inventory_schema",
            lambda _conn: (_ for _ in ()).throw(AssertionError("schema columns are already current")),
        )

        def record_reconcile(*args, **kwargs):
            reconcile_calls.append(kwargs)
            return {"current_quantity": 3}

        monkeypatch.setattr(inventory_identity_service, "reconcile_inventory_total", record_reconcile)

        inventory_identity_service.apply_inventory_purchase_by_identity(
            conn,
            household_id="hh-1",
            household_article_id="article-1",
            quantity=1,
            space_id=None,
            sublocation_id=None,
        )

    assert len(reconcile_calls) == 1
    assert reconcile_calls[0]["household_id"] == "hh-1"
    assert reconcile_calls[0]["household_article_id"] == "article-1"
