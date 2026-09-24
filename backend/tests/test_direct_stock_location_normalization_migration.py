from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260924_01_normalize_direct_stock_location.py"
    )
    spec = importlib.util.spec_from_file_location("direct_stock_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE spaces (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                is_direct INTEGER DEFAULT 0,
                system_key TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE sublocations (
                id TEXT PRIMARY KEY,
                space_id TEXT NOT NULL,
                naam TEXT,
                system_key TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                default_inventory_handling TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT NOT NULL,
                aantal NUMERIC,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT DEFAULT 'active',
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT,
                location_id TEXT,
                location_label TEXT,
                event_type TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                matched_household_article_id TEXT,
                target_location_id TEXT,
                suggested_location_id TEXT,
                final_location_id TEXT,
                location_override_mode TEXT,
                updated_at TEXT
            )
        """))

        conn.execute(text("""
            INSERT INTO spaces (id, household_id, naam, is_direct, system_key) VALUES
              ('direct-space', 'h1', 'Direct', 1, 'system.direct'),
              ('normal-space', 'h1', 'Keuken', 0, NULL)
        """))
        conn.execute(text("""
            INSERT INTO sublocations (id, space_id, naam, system_key) VALUES
              ('direct-sub', 'direct-space', 'Direct', 'system.direct')
        """))
        conn.execute(text("""
            INSERT INTO household_articles (id, household_id, default_inventory_handling) VALUES
              ('stock-article', 'h1', 'STOCK'),
              ('direct-article', 'h1', 'DIRECT_CONSUMPTION')
        """))
        conn.execute(text("""
            INSERT INTO inventory (
                id, household_id, household_article_id, aantal, space_id, sublocation_id, status
            ) VALUES
              ('stock-locationless', 'h1', 'stock-article', 3, NULL, NULL, 'active'),
              ('stock-on-direct', 'h1', 'stock-article', 2, 'direct-space', NULL, 'active'),
              ('consume-on-direct', 'h1', 'direct-article', 4, 'direct-space', 'direct-sub', 'active')
        """))
        conn.execute(text("""
            INSERT INTO inventory_events (
                id, household_id, household_article_id, location_id, location_label, event_type
            ) VALUES
              ('stock-purchase', 'h1', 'stock-article', 'direct-space', 'Direct', 'purchase'),
              ('direct-purchase', 'h1', 'direct-article', 'direct-space', 'Direct', 'purchase')
        """))
        conn.execute(text("""
            INSERT INTO purchase_import_batches (id, household_id)
            VALUES ('batch-1', 'h1')
        """))
        conn.execute(text("""
            INSERT INTO purchase_import_lines (
                id, batch_id, matched_household_article_id, target_location_id,
                suggested_location_id, final_location_id, location_override_mode
            ) VALUES
              ('stock-line', 'batch-1', 'stock-article', 'direct-space',
               'direct-space', 'direct-space', 'auto'),
              ('direct-line', 'batch-1', 'direct-article', 'direct-space',
               'direct-space', 'direct-space', 'auto')
        """))
    return engine


def test_migration_preserves_stock_quantity_but_removes_direct_as_stock_location():
    module = _load_migration()
    engine = _engine()

    with engine.begin() as conn:
        module.op.get_bind = lambda: conn
        module.upgrade()

        stock_rows = conn.execute(text("""
            SELECT id, aantal, space_id, sublocation_id
            FROM inventory
            WHERE household_id = 'h1'
              AND household_article_id = 'stock-article'
              AND COALESCE(status, 'active') = 'active'
        """)).mappings().all()
        direct_inventory_count = conn.execute(text("""
            SELECT COUNT(*)
            FROM inventory
            WHERE household_id = 'h1'
              AND household_article_id = 'direct-article'
        """)).scalar_one()
        stock_event = conn.execute(text("""
            SELECT location_id, location_label
            FROM inventory_events
            WHERE id = 'stock-purchase'
        """)).mappings().one()
        direct_event = conn.execute(text("""
            SELECT location_id, location_label
            FROM inventory_events
            WHERE id = 'direct-purchase'
        """)).mappings().one()
        stock_line = conn.execute(text("""
            SELECT target_location_id, suggested_location_id, final_location_id,
                   location_override_mode
            FROM purchase_import_lines
            WHERE id = 'stock-line'
        """)).mappings().one()
        direct_line = conn.execute(text("""
            SELECT target_location_id, final_location_id
            FROM purchase_import_lines
            WHERE id = 'direct-line'
        """)).mappings().one()

    assert len(stock_rows) == 1
    assert float(stock_rows[0]["aantal"]) == 5.0
    assert stock_rows[0]["space_id"] is None
    assert stock_rows[0]["sublocation_id"] is None
    assert int(direct_inventory_count) == 0

    assert stock_event["location_id"] is None
    assert stock_event["location_label"] is None
    assert direct_event["location_id"] == "direct-space"
    assert direct_event["location_label"] == "Direct"

    assert stock_line["target_location_id"] is None
    assert stock_line["suggested_location_id"] is None
    assert stock_line["final_location_id"] is None
    assert stock_line["location_override_mode"] == "cleared"
    assert direct_line["target_location_id"] == "direct-space"
    assert direct_line["final_location_id"] == "direct-space"
