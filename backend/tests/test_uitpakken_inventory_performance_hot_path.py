from sqlalchemy import create_engine, text

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
