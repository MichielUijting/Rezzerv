import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.services.canonical_inventory_identity_service import (
    LOCATIONLESS_ACTIVE_IDENTITY_INDEX,
    apply_inventory_purchase_by_identity,
    ensure_locationless_inventory_identity_guard,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _seed_schema(conn, *, with_identity_index: bool = True):
    conn.execute(text("""
        CREATE TABLE household_articles (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            naam TEXT,
            status TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE inventory (
            id TEXT PRIMARY KEY,
            naam TEXT,
            aantal INTEGER,
            household_id TEXT,
            household_article_id TEXT,
            space_id TEXT,
            sublocation_id TEXT,
            status TEXT,
            updated_at TEXT
        )
    """))
    if with_identity_index:
        conn.execute(text(f"""
            CREATE UNIQUE INDEX {LOCATIONLESS_ACTIVE_IDENTITY_INDEX}
            ON inventory (household_id, household_article_id)
            WHERE COALESCE(status, 'active') = 'active'
              AND household_article_id IS NOT NULL
              AND space_id IS NULL
              AND sublocation_id IS NULL
        """))
    conn.execute(text("""
        INSERT INTO household_articles (id, household_id, naam, status)
        VALUES ('article-1', 'house-1', 'Melk', 'active')
    """))


def test_locationless_purchases_merge_into_one_active_null_null_identity():
    engine = _engine()
    with engine.begin() as conn:
        _seed_schema(conn)

        first_id = apply_inventory_purchase_by_identity(
            conn,
            household_id="house-1",
            household_article_id="article-1",
            quantity=2,
            space_id=None,
            sublocation_id=None,
        )
        second_id = apply_inventory_purchase_by_identity(
            conn,
            household_id="house-1",
            household_article_id="article-1",
            quantity=3,
            space_id=None,
            sublocation_id=None,
        )

        assert second_id == first_id
        row = conn.execute(text("""
            SELECT id, aantal, space_id, sublocation_id
            FROM inventory
            WHERE household_id = 'house-1'
              AND household_article_id = 'article-1'
              AND COALESCE(status, 'active') = 'active'
        """)).mappings().one()
        assert row["id"] == first_id
        assert row["aantal"] == 5
        assert row["space_id"] is None
        assert row["sublocation_id"] is None

        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO inventory (
                    id, naam, aantal, household_id, household_article_id,
                    space_id, sublocation_id, status, updated_at
                ) VALUES (
                    'duplicate', 'Melk', 1, 'house-1', 'article-1',
                    NULL, NULL, 'active', CURRENT_TIMESTAMP
                )
            """))


def test_guard_reports_preexisting_locationless_duplicates_before_index_validation():
    engine = _engine()
    with engine.begin() as conn:
        _seed_schema(conn, with_identity_index=False)
        conn.execute(text("""
            INSERT INTO inventory (
                id, naam, aantal, household_id, household_article_id,
                space_id, sublocation_id, status, updated_at
            ) VALUES
                ('duplicate-1', 'Melk', 1, 'house-1', 'article-1', NULL, NULL, 'active', CURRENT_TIMESTAMP),
                ('duplicate-2', 'Melk', 1, 'house-1', 'article-1', NULL, NULL, 'active', CURRENT_TIMESTAMP)
        """))

        with pytest.raises(RuntimeError) as exc_info:
            ensure_locationless_inventory_identity_guard(conn)
        assert "Dubbele actieve locationless voorraadidentiteit" in str(exc_info.value)


def test_missing_locationless_index_fails_closed_without_runtime_schema_mutation():
    engine = _engine()
    with engine.begin() as conn:
        _seed_schema(conn, with_identity_index=False)
        before = tuple(conn.execute(text(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        )).all())

        with pytest.raises(RuntimeError, match="index ontbreekt"):
            ensure_locationless_inventory_identity_guard(conn)

        after = tuple(conn.execute(text(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        )).all())
        assert after == before
        assert conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
            {"name": LOCATIONLESS_ACTIVE_IDENTITY_INDEX},
        ).scalar() is None

def test_wrong_locationless_predicate_is_rejected_even_with_matching_tokens():
    engine = _engine()
    with engine.begin() as conn:
        _seed_schema(conn, with_identity_index=False)
        conn.execute(text(f"""
            CREATE UNIQUE INDEX {LOCATIONLESS_ACTIVE_IDENTITY_INDEX}
            ON inventory (household_id, household_article_id)
            WHERE COALESCE(status, 'active') <> 'active'
              AND household_article_id IS NOT NULL
              AND space_id IS NULL
              AND sublocation_id IS NULL
        """))

        with pytest.raises(RuntimeError, match="predicate wijkt af"):
            ensure_locationless_inventory_identity_guard(conn)

