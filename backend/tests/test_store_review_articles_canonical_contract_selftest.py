"""Self-contained Slice 2B2 contract test.

Run with:
  PYTHONPATH=/app python tests/test_store_review_articles_canonical_contract_selftest.py
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.household_article_option_service import list_canonical_household_article_options


def main() -> int:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                article_group_id TEXT,
                brand_or_maker TEXT,
                consumable INTEGER,
                status TEXT DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_article_settings (
                household_article_id TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL
            )
        """))

        conn.execute(text("""
            INSERT INTO household_articles
                (id, household_id, naam, article_group_id, brand_or_maker, consumable, status)
            VALUES
                ('ha-a-1', 'A', 'Melk', 'group-1', 'Campina', 1, 'active'),
                ('ha-a-2', 'A', 'Pasta', NULL, '', 1, 'active'),
                ('ha-a-archived', 'A', 'Oud artikel', NULL, '', 1, 'archived'),
                ('ha-b-1', 'B', 'Banaan', NULL, '', 1, 'active')
        """))
        conn.execute(text("""
            INSERT INTO household_article_settings
                (household_article_id, setting_key, setting_value)
            VALUES
                ('ha-a-1', 'default_location_id', '"space-1"'),
                ('ha-a-1', 'default_sublocation_id', '"shelf-1"')
        """))
        conn.execute(text("""
            INSERT INTO inventory (id, household_id, naam)
            VALUES ('inv-a-1', 'A', 'Losse voorraadnaam')
        """))

        items = list_canonical_household_article_options(conn, 'A')
        assert [item['id'] for item in items] == ['ha-a-1', 'ha-a-2'], items
        assert all(item['id'] == item['household_article_id'] for item in items), items
        assert all(not item['id'].startswith('live::') for item in items), items
        assert all(item['id'] not in {'1', '2', '3', '4', '5'} for item in items), items
        assert all(item['name'] != 'Losse voorraadnaam' for item in items), items
        assert all(item['name'] != 'Banaan' for item in items), items
        assert all(item['name'] != 'Oud artikel' for item in items), items
        assert items[0]['article_group_id'] == 'group-1', items[0]
        assert items[0]['default_location_id'] == 'space-1', items[0]
        assert items[0]['default_sublocation_id'] == 'shelf-1', items[0]

        filtered = list_canonical_household_article_options(conn, 'A', 'campina')
        assert len(filtered) == 1 and filtered[0]['id'] == 'ha-a-1', filtered

    print('PASS household isolation')
    print('PASS canonical id equals household_article_id')
    print('PASS no live aliases or mock ids')
    print('PASS inventory-only names excluded')
    print('PASS inactive household articles excluded')
    print('PASS article group and location defaults preserved')
    print('STORE_REVIEW_ARTICLES_CANONICAL_CONTRACT_GREEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
