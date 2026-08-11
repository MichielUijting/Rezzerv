from sqlalchemy import create_engine, text

from app.api.superuser_household_routes import _shopping_rows


def test_superuser_winkelen_reads_only_current_active_shopping_list_with_user_facing_fields():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE shopping_lists (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE shopping_list_items (
                id TEXT PRIMARY KEY,
                shopping_list_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                article_name TEXT NOT NULL,
                product_type_name TEXT,
                size TEXT,
                note TEXT,
                checked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO shopping_lists(id, household_id, status, created_at) VALUES
              ('active-list', 'hh-1', 'active', '2026-08-11T10:00:00'),
              ('old-list', 'hh-1', 'completed', '2026-08-10T10:00:00'),
              ('other-list', 'hh-2', 'active', '2026-08-11T10:00:00')
        """))
        conn.execute(text("""
            INSERT INTO shopping_list_items(
                id, shopping_list_id, household_id, article_name, product_type_name, size, note, checked, created_at
            ) VALUES
              ('1', 'active-list', 'hh-1', 'Melk', 'Volle melk', '1 liter', 'Voor koffie', 0, '2026-08-11T10:01:00'),
              ('2', 'active-list', 'hh-1', 'Brood', 'Volkorenbrood', '800 g', '', 1, '2026-08-11T10:02:00'),
              ('3', 'old-list', 'hh-1', 'Oud artikel', 'Historisch', '1 stuk', '', 0, '2026-08-10T10:01:00'),
              ('4', 'other-list', 'hh-2', 'Ander huishouden', 'Test', '1 stuk', '', 0, '2026-08-11T10:01:00')
        """))

        rows = _shopping_rows(conn, 'hh-1')

    assert [row['id'] for row in rows] == ['1', '2']
    assert rows[0] == {
        'id': '1',
        'article_name': 'Melk',
        'product_type_name': 'Volle melk',
        'size': '1 liter',
        'note': 'Voor koffie',
        'checked': 0,
    }
    assert rows[1]['checked'] == 1


def test_superuser_winkelen_frontend_uses_same_visible_semantics_as_regular_winkelen():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = (root / 'frontend/src/features/superuser/SuperuserDashboardPage.jsx').read_text(encoding='utf-8')
    assert "winkelen: ['id', 'article_name', 'product_type_name', 'size', 'note', 'checked']" in source
    for key, label in (
        ('article_name', 'Artikel'),
        ('product_type_name', 'Producttype'),
        ('size', 'Omvang'),
        ('note', 'Notitie'),
        ('checked', 'Gekocht'),
    ):
        assert f"{key}: '{label}'" in source
    assert "normalizedKey === 'checked'" in source
    assert "? 'Ja' : 'Nee'" in source
