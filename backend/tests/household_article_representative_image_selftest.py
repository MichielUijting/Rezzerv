from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.household_article_representative_image_service import (
    backfill_household_article_representative_products,
    ensure_representative_product_for_household_article,
    representative_image_urls_for_household_articles,
)


def _engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for statement in (
            """
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                global_product_id TEXT,
                barcode TEXT
            )
            """,
            """
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY,
                primary_gtin TEXT,
                image_url TEXT,
                status TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE global_product_gpc_bricks (
                global_product_id TEXT PRIMARY KEY,
                brick_code TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE product_identities (
                household_article_id TEXT,
                global_product_id TEXT
            )
            """,
            """
            CREATE TABLE purchase_import_lines (
                matched_household_article_id TEXT,
                matched_global_product_id TEXT
            )
            """,
            """
            CREATE TABLE household_article_representative_products (
                household_article_id TEXT PRIMARY KEY,
                global_product_id TEXT NOT NULL,
                brick_code TEXT NOT NULL,
                selection_source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ):
            conn.execute(text(statement))
    return engine


def _seed(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO global_products (
                id, primary_gtin, image_url, status, updated_at
            ) VALUES
                ('generic-broccoli', '', NULL, 'active', '2026-09-19T10:00:00'),
                ('picnic-broccoli', '8711578582950', 'https://images.example.test/broccoli-picnic.jpg', 'active', '2026-09-20T10:00:00'),
                ('ah-broccoli', '8710000000001', 'https://images.example.test/broccoli-ah.jpg', 'active', '2026-09-19T12:00:00'),
                ('unrelated-product', '8710000000002', 'https://images.example.test/unrelated.jpg', 'active', '2026-09-21T10:00:00'),
                ('generic-other', '', NULL, 'active', '2026-09-19T10:00:00')
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO global_product_gpc_bricks (
                global_product_id, brick_code
            ) VALUES
                ('generic-broccoli', '10000001'),
                ('picnic-broccoli', '10000001'),
                ('ah-broccoli', '10000001'),
                ('unrelated-product', '20000002'),
                ('generic-other', '30000003')
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO household_articles (
                id, household_id, global_product_id, barcode
            ) VALUES
                ('article-broccoli', 'household-1', 'generic-broccoli', NULL),
                ('article-history', 'household-1', NULL, NULL),
                ('article-other', 'household-1', 'generic-other', NULL)
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_lines (
                matched_household_article_id,
                matched_global_product_id
            ) VALUES ('article-history', 'ah-broccoli')
            """
        )
    )


def test_backfill_selects_exact_photo_inside_same_gpc_brick() -> None:
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        report = backfill_household_article_representative_products(conn)
        selected = conn.execute(
            text(
                """
                SELECT global_product_id, brick_code, selection_source
                FROM household_article_representative_products
                WHERE household_article_id = 'article-broccoli'
                """
            )
        ).mappings().one()

        assert report["scanned"] == 3
        assert report["selected"] == 2
        assert report["unresolved"] == 1
        assert selected["global_product_id"] == "picnic-broccoli"
        assert selected["brick_code"] == "10000001"
        assert selected["selection_source"] == "same_gpc_brick_catalog"

        history_selected = conn.execute(
            text(
                """
                SELECT global_product_id, brick_code, selection_source
                FROM household_article_representative_products
                WHERE household_article_id = 'article-history'
                """
            )
        ).mappings().one()
        assert history_selected["global_product_id"] == "ah-broccoli"
        assert history_selected["brick_code"] == "10000001"
        assert history_selected["selection_source"] == "purchase_history"

        images = representative_image_urls_for_household_articles(
            conn,
            [{
                "id": "article-broccoli",
                "global_product_id": "generic-broccoli",
                "barcode": None,
            }],
        )
        assert images == {
            "article-broccoli": "https://images.example.test/broccoli-picnic.jpg"
        }
    engine.dispose()


def test_representative_stays_stable_and_never_crosses_brick() -> None:
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        first = ensure_representative_product_for_household_article(
            conn,
            "article-broccoli",
        )
        assert first["global_product_id"] == "picnic-broccoli"

        conn.execute(
            text(
                """
                INSERT INTO global_products (
                    id, primary_gtin, image_url, status, updated_at
                ) VALUES (
                    'newer-broccoli',
                    '8710000000003',
                    'https://images.example.test/newer-broccoli.jpg',
                    'active',
                    '2026-09-21T12:00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO global_product_gpc_bricks (
                    global_product_id, brick_code
                ) VALUES ('newer-broccoli', '10000001')
                """
            )
        )

        second = ensure_representative_product_for_household_article(
            conn,
            "article-broccoli",
        )
        assert second["status"] == "kept"
        assert second["global_product_id"] == "picnic-broccoli"

        stored = conn.execute(
            text(
                """
                SELECT global_product_id, brick_code
                FROM household_article_representative_products
                WHERE household_article_id = 'article-broccoli'
                """
            )
        ).mappings().one()
        assert stored["global_product_id"] == "picnic-broccoli"
        assert stored["brick_code"] == "10000001"

        other = ensure_representative_product_for_household_article(
            conn,
            "article-other",
        )
        assert other["status"] == "unresolved"
        assert conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM household_article_representative_products
                WHERE household_article_id = 'article-other'
                """
            )
        ).scalar_one() == 0
    engine.dispose()


def test_representative_reads_current_catalog_image_without_copying_url() -> None:
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        ensure_representative_product_for_household_article(
            conn,
            "article-broccoli",
        )
        conn.execute(
            text(
                """
                UPDATE global_products
                SET image_url = 'https://images.example.test/broccoli-updated.jpg'
                WHERE id = 'picnic-broccoli'
                """
            )
        )
        images = representative_image_urls_for_household_articles(
            conn,
            [{
                "id": "article-broccoli",
                "global_product_id": "generic-broccoli",
                "barcode": None,
            }],
        )
        assert images["article-broccoli"] == (
            "https://images.example.test/broccoli-updated.jpg"
        )
    engine.dispose()


def run_contract() -> None:
    test_backfill_selects_exact_photo_inside_same_gpc_brick()
    test_representative_stays_stable_and_never_crosses_brick()
    test_representative_reads_current_catalog_image_without_copying_url()
    print("HOUSEHOLD_ARTICLE_REPRESENTATIVE_IMAGE_GREEN")


if __name__ == "__main__":
    run_contract()
