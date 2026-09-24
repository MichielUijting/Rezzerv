from types import SimpleNamespace

from sqlalchemy import create_engine, text

from app.services.receipt_direct_inventory_approval_patch import (
    _prepare_receipt_batch_for_direct_inventory,
)


def test_direct_kassa_to_inventory_clears_synthetic_direct_target():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                article_name_raw TEXT,
                matched_household_article_id TEXT,
                matched_global_product_id TEXT,
                external_article_code TEXT,
                brand_raw TEXT,
                suggested_household_article_id TEXT,
                match_status TEXT,
                review_decision TEXT,
                target_location_id TEXT,
                suggested_location_id TEXT,
                article_override_mode TEXT,
                location_override_mode TEXT,
                ui_sort_order INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """))
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_lines (
                    id, batch_id, article_name_raw, matched_household_article_id,
                    suggested_household_article_id, match_status, review_decision,
                    target_location_id, suggested_location_id, article_override_mode,
                    location_override_mode, ui_sort_order
                ) VALUES (
                    'line-1', 'batch-1', 'Melk', 'article-1',
                    'article-1', 'matched', 'selected',
                    'legacy-direct-space', 'legacy-direct-space', 'auto',
                    'auto', 1
                )
                """
            )
        )

        main_module = SimpleNamespace(
            normalize_household_article_name=lambda value: str(value).strip(),
            ensure_household_article_for_global_product=lambda *args, **kwargs: None,
            ensure_household_article=lambda *args, **kwargs: "article-created",
            update_batch_status=lambda *args, **kwargs: None,
        )
        configuration = SimpleNamespace(
            location_tracking_level="global",
            unpacking_enabled=False,
        )

        prepared = _prepare_receipt_batch_for_direct_inventory(
            main_module,
            conn,
            batch_id="batch-1",
            household_id="house-1",
            configuration=configuration,
        )

        row = conn.execute(
            text(
                """
                SELECT target_location_id, suggested_location_id, location_override_mode
                FROM purchase_import_lines
                WHERE id = 'line-1'
                """
            )
        ).mappings().one()

    assert prepared == 1
    assert row["target_location_id"] is None
    assert row["suggested_location_id"] is None
    assert row["location_override_mode"] == "cleared"
