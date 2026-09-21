from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.household_representative_image_service import (
    materialize_household_representative_images,
)


ARTICLE_ID = "article-broccoli"
GROUP_ID = "group-broccoli"
BRICK_CODE = "10000164"


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                global_product_id TEXT,
                article_group_id TEXT,
                representative_image_url TEXT,
                representative_image_global_product_id TEXT,
                representative_image_gpc_brick_code TEXT
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE article_groups (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE gpc_bricks (
                brick_code TEXT PRIMARY KEY,
                description TEXT
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE gpc_translations (
                entity_type TEXT,
                entity_code TEXT,
                language_code TEXT,
                translated_text TEXT
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY,
                primary_gtin TEXT,
                image_url TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE global_product_gpc_bricks (
                global_product_id TEXT,
                brick_code TEXT
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                matched_household_article_id TEXT,
                matched_global_product_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.execute(
            text("INSERT INTO article_groups(id, household_id, name) VALUES (:id, 'household-a', 'Broccoli')"),
            {"id": GROUP_ID},
        )
        conn.execute(
            text("INSERT INTO gpc_bricks(brick_code, description) VALUES (:code, 'Broccoli')"),
            {"code": BRICK_CODE},
        )
        conn.execute(
            text("""
                INSERT INTO household_articles(
                    id, household_id, article_group_id
                ) VALUES (:id, 'household-a', :group_id)
            """),
            {"id": ARTICLE_ID, "group_id": GROUP_ID},
        )
        conn.execute(
            text("""
                INSERT INTO global_products(
                    id, primary_gtin, image_url, status, created_at, updated_at
                ) VALUES (
                    'exact-broccoli-picnic',
                    '8711578582950',
                    'https://images.example.test/broccoli.jpg',
                    'active',
                    '2026-09-20T10:00:00',
                    '2026-09-20T10:00:00'
                )
            """)
        )
        conn.execute(
            text("""
                INSERT INTO global_product_gpc_bricks(global_product_id, brick_code)
                VALUES ('exact-broccoli-picnic', :brick_code)
            """),
            {"brick_code": BRICK_CODE},
        )
    return engine


def test_materializes_stable_household_image_from_exact_product_in_same_brick():
    engine = _engine()

    with engine.begin() as conn:
        resolved = materialize_household_representative_images(conn, [ARTICLE_ID])
        assert resolved == {
            ARTICLE_ID: "https://images.example.test/broccoli.jpg"
        }

        row = conn.execute(
            text("""
                SELECT representative_image_url,
                       representative_image_global_product_id,
                       representative_image_gpc_brick_code
                FROM household_articles
                WHERE id = :id
            """),
            {"id": ARTICLE_ID},
        ).mappings().one()

        assert row["representative_image_url"] == "https://images.example.test/broccoli.jpg"
        assert row["representative_image_global_product_id"] == "exact-broccoli-picnic"
        assert row["representative_image_gpc_brick_code"] == BRICK_CODE


def test_representative_image_remains_stable_when_another_store_product_is_added():
    engine = _engine()

    with engine.begin() as conn:
        materialize_household_representative_images(conn, [ARTICLE_ID])
        conn.execute(
            text("""
                INSERT INTO global_products(
                    id, primary_gtin, image_url, status, created_at, updated_at
                ) VALUES (
                    'exact-broccoli-ah',
                    '8719999999999',
                    'https://images.example.test/broccoli-ah.jpg',
                    'active',
                    '2026-09-21T10:00:00',
                    '2026-09-21T10:00:00'
                )
            """)
        )
        conn.execute(
            text("""
                INSERT INTO global_product_gpc_bricks(global_product_id, brick_code)
                VALUES ('exact-broccoli-ah', :brick_code)
            """),
            {"brick_code": BRICK_CODE},
        )

        second = materialize_household_representative_images(conn, [ARTICLE_ID])
        assert second == {}

        row = conn.execute(
            text("""
                SELECT representative_image_url,
                       representative_image_global_product_id
                FROM household_articles
                WHERE id = :id
            """),
            {"id": ARTICLE_ID},
        ).mappings().one()

        assert row["representative_image_url"] == "https://images.example.test/broccoli.jpg"
        assert row["representative_image_global_product_id"] == "exact-broccoli-picnic"
