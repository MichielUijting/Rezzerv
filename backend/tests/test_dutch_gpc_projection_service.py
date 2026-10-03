from sqlalchemy import create_engine, text

from app.services.dutch_gpc_projection_service import (
    dutch_gpc_by_global_product,
    dutch_gpc_by_household_article,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE global_product_gpc_bricks (
                global_product_id TEXT NOT NULL,
                brick_code TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE gpc_product_groups (
                gpc_brick_code TEXT PRIMARY KEY,
                gpc_brick_name TEXT,
                gpc_class_code TEXT,
                gpc_class_name TEXT,
                gpc_family_code TEXT,
                gpc_family_name TEXT,
                gpc_segment_code TEXT,
                gpc_segment_name TEXT,
                language_code TEXT,
                active INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                global_product_id TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO global_product_gpc_bricks(global_product_id, brick_code)
            VALUES ('gp-1', '10000001'), ('gp-2', '10000002')
        """))
        conn.execute(text("""
            INSERT INTO gpc_product_groups(
                gpc_brick_code, gpc_brick_name, gpc_class_code, gpc_class_name,
                gpc_family_code, gpc_family_name, gpc_segment_code, gpc_segment_name,
                language_code, active
            ) VALUES
            ('10000001', 'Bananen', '20000001', 'Vers fruit',
             '30000001', 'Fruit - onbereid/onbewerkt (vers)',
             '40000001', 'Voedingsmiddelen', 'nl', 1),
            ('10000002', 'English only', '20000002', 'English class',
             '30000002', 'English family',
             '40000002', 'English segment', 'en', 1)
        """))
        conn.execute(text("""
            INSERT INTO household_articles(id, household_id, global_product_id)
            VALUES
            ('ha-1', 'h1', 'gp-1'),
            ('ha-2', 'h1', 'gp-2'),
            ('ha-other', 'h2', 'gp-1')
        """))
    return engine


def test_dutch_gpc_by_global_product_uses_only_dutch_reference_rows():
    engine = _engine()
    try:
        with engine.begin() as conn:
            payload = dutch_gpc_by_global_product(conn, ['gp-1', 'gp-2'])
        assert payload == {
            'gp-1': {
                'gpc_brick_code': '10000001',
                'gpc_brick_name': 'Bananen',
                'gpc_class_code': '20000001',
                'gpc_class_name': 'Vers fruit',
                'gpc_family_code': '30000001',
                'gpc_family_name': 'Fruit - onbereid/onbewerkt (vers)',
                'gpc_segment_code': '40000001',
                'gpc_segment_name': 'Voedingsmiddelen',
            }
        }
    finally:
        engine.dispose()


def test_dutch_gpc_by_household_article_respects_household_boundary():
    engine = _engine()
    try:
        with engine.begin() as conn:
            payload = dutch_gpc_by_household_article(conn, 'h1', ['ha-1', 'ha-other'])
        assert set(payload) == {'ha-1'}
        assert payload['ha-1']['gpc_brick_name'] == 'Bananen'
        assert payload['ha-1']['gpc_family_name'] == 'Fruit - onbereid/onbewerkt (vers)'
    finally:
        engine.dispose()
