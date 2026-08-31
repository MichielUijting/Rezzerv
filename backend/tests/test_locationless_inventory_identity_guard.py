import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.services.canonical_inventory_identity_service import (
    LOCATIONLESS_ACTIVE_IDENTITY_INDEX,
    apply_inventory_purchase_by_identity,
    ensure_locationless_inventory_identity_guard,
)


def _required_url(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} ontbreekt voor PostgreSQL inventory identity tests")
    return value


def _engines():
    schema_engine = create_engine(_required_url("TEST_SCHEMA_DATABASE_URL"), future=True)
    runtime_engine = create_engine(_required_url("DATABASE_URL"), future=True)
    if schema_engine.dialect.name != "postgresql" or runtime_engine.dialect.name != "postgresql":
        schema_engine.dispose()
        runtime_engine.dispose()
        raise RuntimeError("Locationless inventory identity tests vereisen PostgreSQL")
    return schema_engine, runtime_engine


def _drop_schema(schema_engine) -> None:
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS inventory"))
        conn.execute(text("DROP TABLE IF EXISTS household_articles"))


def _seed_schema(schema_engine, *, with_identity_index: bool = True) -> None:
    _drop_schema(schema_engine)
    with schema_engine.begin() as conn:
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
                updated_at TIMESTAMPTZ
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
    schema_engine, runtime_engine = _engines()
    try:
        _seed_schema(schema_engine)
        with runtime_engine.begin() as conn:
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
                with conn.begin_nested():
                    conn.execute(text("""
                        INSERT INTO inventory (
                            id, naam, aantal, household_id, household_article_id,
                            space_id, sublocation_id, status, updated_at
                        ) VALUES (
                            'duplicate', 'Melk', 1, 'house-1', 'article-1',
                            NULL, NULL, 'active', CURRENT_TIMESTAMP
                        )
                    """))
    finally:
        _drop_schema(schema_engine)
        schema_engine.dispose()
        runtime_engine.dispose()


def test_guard_reports_preexisting_locationless_duplicates_before_index_validation():
    schema_engine, runtime_engine = _engines()
    try:
        _seed_schema(schema_engine, with_identity_index=False)
        with runtime_engine.begin() as conn:
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
    finally:
        _drop_schema(schema_engine)
        schema_engine.dispose()
        runtime_engine.dispose()


def test_missing_locationless_index_fails_closed_without_runtime_schema_mutation():
    schema_engine, runtime_engine = _engines()
    try:
        _seed_schema(schema_engine, with_identity_index=False)
        with runtime_engine.begin() as conn:
            before = inspect(conn).get_indexes("inventory")

            with pytest.raises(RuntimeError, match="index ontbreekt"):
                ensure_locationless_inventory_identity_guard(conn)

            after = inspect(conn).get_indexes("inventory")
            assert after == before
            assert not any(
                str(index.get("name") or "") == LOCATIONLESS_ACTIVE_IDENTITY_INDEX
                for index in after
            )
    finally:
        _drop_schema(schema_engine)
        schema_engine.dispose()
        runtime_engine.dispose()


def test_runtime_guard_leaves_exact_partial_predicate_authority_to_alembic():
    schema_engine, runtime_engine = _engines()
    try:
        _seed_schema(schema_engine, with_identity_index=False)
        with schema_engine.begin() as conn:
            conn.execute(text(f"""
                CREATE UNIQUE INDEX {LOCATIONLESS_ACTIVE_IDENTITY_INDEX}
                ON inventory (household_id, household_article_id)
                WHERE COALESCE(status, 'active') <> 'active'
                  AND household_article_id IS NOT NULL
                  AND space_id IS NULL
                  AND sublocation_id IS NULL
            """))

        # Runtime validates the migration-owned index name/uniqueness and current
        # duplicate invariant only. Revision 20260828_03 owns the exact predicate.
        with runtime_engine.begin() as conn:
            ensure_locationless_inventory_identity_guard(conn)
    finally:
        _drop_schema(schema_engine)
        schema_engine.dispose()
        runtime_engine.dispose()
