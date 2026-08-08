from sqlalchemy import create_engine, text

from app.services.direct_inventory_cleanup_service import cleanup_direct_inventory_artifacts


def _engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE spaces (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE sublocations (
                id TEXT PRIMARY KEY,
                space_id TEXT NOT NULL,
                naam TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT,
                naam TEXT,
                aantal INTEGER,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                household_article_id TEXT,
                event_type TEXT,
                quantity INTEGER
            )
        """))
        conn.execute(text("""
            INSERT INTO spaces (id, household_id, naam) VALUES
              ('direct-space-1', '1', 'Direct'),
              ('bathroom-1', '1', 'Badkamer'),
              ('direct-space-2', '2', 'Direct')
        """))
        conn.execute(text("""
            INSERT INTO sublocations (id, space_id, naam) VALUES
              ('direct-sub-1', 'direct-space-1', 'Direct'),
              ('cabinet-1', 'bathroom-1', 'Kast'),
              ('direct-sub-2', 'direct-space-2', 'Direct')
        """))
        conn.execute(text("""
            INSERT INTO inventory
                (id, household_id, household_article_id, naam, aantal, space_id, sublocation_id)
            VALUES
              ('stale-apple', '1', 'apple-1', 'Appel', 1, 'direct-space-1', 'direct-sub-1'),
              ('physical-apple', '1', 'apple-1', 'Appel', 2, 'bathroom-1', 'cabinet-1'),
              ('other-household', '2', 'apple-2', 'Appel', 4, 'direct-space-2', 'direct-sub-2')
        """))
        conn.execute(text("""
            INSERT INTO inventory_events
                (id, household_id, household_article_id, event_type, quantity)
            VALUES ('purchase-history', '1', 'apple-1', 'purchase', 1)
        """))
    return engine


def test_dry_run_reports_direct_stock_without_mutating_anything():
    engine = _engine()
    report = cleanup_direct_inventory_artifacts(engine, dry_run=True, household_id='1')
    assert report.stale_rows == 1
    assert report.stale_quantity == 1
    assert report.removed_rows == 0
    assert report.details[0]['article_name'] == 'Appel'

    with engine.begin() as conn:
        total = conn.execute(text("SELECT SUM(aantal) FROM inventory WHERE household_id='1' AND household_article_id='apple-1'" )).scalar_one()
        assert int(total) == 3


def test_apply_removes_only_direct_direct_stock_and_preserves_history():
    engine = _engine()
    report = cleanup_direct_inventory_artifacts(engine, dry_run=False, household_id='1')
    assert report.stale_rows == 1
    assert report.stale_quantity == 1
    assert report.removed_rows == 1

    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, aantal, space_id, sublocation_id
            FROM inventory
            WHERE household_id='1' AND household_article_id='apple-1'
        """)).mappings().all()
        assert len(rows) == 1
        assert rows[0]['id'] == 'physical-apple'
        assert int(rows[0]['aantal']) == 2
        history_count = conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE id='purchase-history'" )).scalar_one()
        assert int(history_count) == 1
        other_household_count = conn.execute(text("SELECT COUNT(*) FROM inventory WHERE id='other-household'" )).scalar_one()
        assert int(other_household_count) == 1


def test_apply_is_idempotent():
    engine = _engine()
    first = cleanup_direct_inventory_artifacts(engine, dry_run=False, household_id='1')
    second = cleanup_direct_inventory_artifacts(engine, dry_run=False, household_id='1')
    assert first.removed_rows == 1
    assert second.stale_rows == 0
    assert second.stale_quantity == 0
    assert second.removed_rows == 0
