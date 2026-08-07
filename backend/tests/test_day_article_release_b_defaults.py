from sqlalchemy import create_engine, text

from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    get_default_inventory_handling_batch,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                default_inventory_handling TEXT,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE spaces (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                household_id TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE sublocations (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                space_id TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_articles
                (id, household_id, naam, default_inventory_handling)
            VALUES
                ('article-stock', 'household-1', 'Melk', 'STOCK'),
                ('article-direct', 'household-1', 'Brood', 'DIRECT_CONSUMPTION'),
                ('article-other-household', 'household-2', 'Yoghurt', 'DIRECT_CONSUMPTION'),
                ('article-legacy-null', 'household-1', 'Boter', NULL)
        """))
    return engine


def test_batch_returns_defaults_in_requested_order_and_deduplicates_ids():
    engine = _engine()
    with engine.begin() as conn:
        items = get_default_inventory_handling_batch(
            conn,
            "household-1",
            ["article-direct", "article-stock", "article-direct"],
        )

    assert [item["id"] for item in items] == ["article-direct", "article-stock"]
    assert [item["default_inventory_handling"] for item in items] == [
        DIRECT_CONSUMPTION,
        STOCK,
    ]


def test_batch_treats_legacy_null_default_as_stock():
    engine = _engine()
    with engine.begin() as conn:
        items = get_default_inventory_handling_batch(
            conn,
            "household-1",
            ["article-legacy-null"],
        )

    assert items[0]["default_inventory_handling"] == STOCK


def test_batch_omits_unknown_and_other_household_articles():
    engine = _engine()
    with engine.begin() as conn:
        items = get_default_inventory_handling_batch(
            conn,
            "household-1",
            ["article-stock", "article-other-household", "missing"],
        )

    assert [item["id"] for item in items] == ["article-stock"]
    assert all(item["household_id"] == "household-1" for item in items)


def test_batch_returns_empty_list_for_empty_input():
    engine = _engine()
    with engine.begin() as conn:
        items = get_default_inventory_handling_batch(conn, "household-1", [])

    assert items == []
