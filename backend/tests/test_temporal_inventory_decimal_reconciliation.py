from decimal import Decimal

from sqlalchemy import create_engine, text

from app.services.temporal_inventory_service import reconcile_inventory_total


def test_reconcile_preserves_exact_fractional_inventory_delta():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
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
                effective_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                effective_at_precision TEXT NOT NULL,
                event_priority INTEGER NOT NULL,
                source_reference TEXT,
                source_line_id TEXT,
                replayed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        conn.execute(text(
            """
            CREATE INDEX idx_inventory_events_temporal_order
            ON inventory_events (
                household_id,
                household_article_id,
                effective_at,
                event_priority,
                id
            )
            """
        ))
        conn.execute(text(
            """
            CREATE INDEX idx_inventory_events_source_reference
            ON inventory_events (source, source_reference, source_line_id)
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                aantal NUMERIC NOT NULL,
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
            INSERT INTO inventory (
                id, naam, aantal, household_id, household_article_id, status
            ) VALUES (
                'I1', 'Melk', 2, 'H1', 'A1', 'active'
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, household_article_id, article_name,
                event_type, quantity, source,
                effective_at, recorded_at, effective_at_precision, event_priority,
                source_reference
            ) VALUES
                (
                    'purchase', 'H1', 'A1', 'A1', 'Melk',
                    'purchase', 2, 'test',
                    '2026-09-09T10:00:00+00:00', '2026-09-09T10:00:00+00:00',
                    'datetime', 10, 'purchase'
                ),
                (
                    'adjustment', 'H1', 'A1', 'A1', 'Melk',
                    'adjustment', -0.765433, 'test',
                    '2026-09-09T11:00:00+00:00', '2026-09-09T11:00:00+00:00',
                    'datetime', 50, 'adjustment'
                )
            """
        ))

        report = reconcile_inventory_total(
            conn,
            household_id="H1",
            household_article_id="A1",
            preferred_inventory_id="I1",
        )
        projected = conn.execute(
            text("SELECT aantal FROM inventory WHERE id='I1'")
        ).scalar_one()

        assert report["current_quantity"] == Decimal("1.234567")
        assert report["projection_delta"] == Decimal("-0.765433")
        assert Decimal(str(projected)) == Decimal("1.234567")
