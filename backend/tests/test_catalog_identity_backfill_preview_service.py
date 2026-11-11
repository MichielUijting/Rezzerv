"""Exact historical receipt lineage must be dry-run and conflict-safe."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.catalog_identity_backfill_preview_service import (
    preview_household_catalog_identity_backfill,
)


def _fixture():
    url = os.environ.get("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Dedicated PostgreSQL identity test database not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_identity_test"):
        raise RuntimeError("Refusing non-isolated identity test database")
    engine = create_engine(url)
    conn = engine.connect()
    statements = [
        "CREATE TEMP TABLE global_products (id TEXT PRIMARY KEY, primary_gtin TEXT, status TEXT)",
        "CREATE TEMP TABLE product_identities (id TEXT, global_product_id TEXT, identity_type TEXT, identity_value TEXT)",
        "CREATE TEMP TABLE external_article_product_links (global_product_id TEXT, retailer_code TEXT, external_article_code TEXT, status TEXT, confirmed_by TEXT DEFAULT NULL)",
        "CREATE TEMP TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT)",
        "CREATE TEMP TABLE receipt_tables (id TEXT PRIMARY KEY, household_id TEXT, store_name TEXT)",
        "CREATE TEMP TABLE receipt_table_lines (id TEXT PRIMARY KEY, receipt_table_id TEXT, barcode TEXT, external_article_code TEXT, is_deleted BOOLEAN)",
        "CREATE TEMP TABLE purchase_import_batches (id TEXT PRIMARY KEY, household_id TEXT, source_reference TEXT, source_type TEXT)",
        "CREATE TEMP TABLE purchase_import_lines (batch_id TEXT, external_line_ref TEXT, matched_household_article_id TEXT)",
    ]
    for sql in statements:
        conn.execute(text(sql))
    conn.execute(text("INSERT INTO global_products VALUES ('p1', NULL, 'active')"))
    conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p1','lidl','code1','confirmed')"))
    conn.execute(text("INSERT INTO household_articles VALUES ('a1','h1',NULL), ('a2','h2',NULL)"))
    conn.execute(text("INSERT INTO receipt_tables VALUES ('r1','h1','lidl'), ('r2','h2','lidl')"))
    conn.execute(text("INSERT INTO receipt_table_lines VALUES ('l1','r1',NULL,'code1',FALSE), ('l2','r2',NULL,'code1',FALSE)"))
    conn.execute(text("INSERT INTO purchase_import_batches VALUES ('b1','h1','receipt:r1','receipt'), ('b2','h2','receipt:r2','receipt')"))
    conn.execute(text("INSERT INTO purchase_import_lines VALUES ('b1','receipt-line:l1','a1'), ('b2','receipt-line:l2','a2')"))
    return engine, conn


def test_preview_is_household_scoped_and_does_not_write():
    engine, conn = _fixture()
    try:
        result = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert result["source_rows_examined"] == 1
        assert result["articles_examined"] == 1
        assert result["eligible"] == 1, result
        assert result["changes"] == "none"
        assert conn.execute(text("SELECT global_product_id FROM household_articles WHERE id='a1'")).scalar() is None
        other = preview_household_catalog_identity_backfill(conn, household_id="h2")
        assert other["eligible"] == 1, other
    finally:
        conn.close()
        engine.dispose()


def test_preview_rejects_existing_owner_in_same_household():
    engine, conn = _fixture()
    try:
        conn.execute(text("INSERT INTO household_articles VALUES ('a3','h1','p1')"))
        result = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert result["eligible"] == 0, result
        assert result["conflict"] == 1, result
    finally:
        conn.close()
        engine.dispose()


def test_preview_rejects_pending_identity():
    engine, conn = _fixture()
    try:
        conn.execute(text("UPDATE external_article_product_links SET status='classification_pending'"))
        result = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert result["eligible"] == 0
        assert result["unresolved"] == 1, result
    finally:
        conn.close()
        engine.dispose()


def test_truncated_preview_never_advertises_write_ready_candidates():
    engine, conn = _fixture()
    try:
        result = preview_household_catalog_identity_backfill(
            conn, household_id="h1", limit=1
        )
        assert result["limited"] is True
        assert result["eligible"] == 0, result
        assert result["eligible_withheld_due_to_limit"] == 1
    finally:
        conn.close()
        engine.dispose()


def test_conflicting_history_for_single_household_article():
    engine, conn = _fixture()
    try:
        conn.execute(text("INSERT INTO global_products VALUES ('p2', NULL, 'active')"))
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id, retailer_code, external_article_code, status) VALUES ('p2','lidl','code2','confirmed')"))
        conn.execute(text("INSERT INTO receipt_table_lines VALUES ('l3','r1',NULL,'code2',FALSE)"))
        conn.execute(text("INSERT INTO purchase_import_lines VALUES ('b1','receipt-line:l3','a1')"))
        result = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert result["conflict"] == 1, result
        assert result["eligible"] == 0, result
    finally:
        conn.close()
        engine.dispose()


def test_reviewed_backfill_updates_only_the_target_household_and_is_repeat_safe():
    from app.services.catalog_identity_backfill_apply_service import (
        apply_reviewed_household_catalog_identity_backfill,
    )

    engine, conn = _fixture()
    try:
        preview = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert preview["eligible"] == 1, preview
        result = apply_reviewed_household_catalog_identity_backfill(
            conn, household_id="h1", reviewed_plan_token=preview["plan_token"],
        )
        assert result["updated"] == 1, result
        assert conn.execute(text(
            "SELECT global_product_id FROM household_articles WHERE id='a1'"
        )).scalar_one() == "p1"
        assert conn.execute(text(
            "SELECT global_product_id FROM household_articles WHERE id='a2'"
        )).scalar_one() is None
        result2 = preview_household_catalog_identity_backfill(conn, household_id="h1")
        assert result2["eligible"] == 0, result2
        assert result2["already_linked"] == 1, result2
        with pytest.raises(ValueError, match="changed"):
            apply_reviewed_household_catalog_identity_backfill(
                conn, household_id="h1", reviewed_plan_token=preview["plan_token"],
            )
        assert result["inventory_changes"] == result["receipt_changes"] == 0
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_reviewed_backfill_rejects_new_conflicts_and_wrong_token():
    from app.services.catalog_identity_backfill_apply_service import (
        apply_reviewed_household_catalog_identity_backfill,
    )

    engine, conn = _fixture()
    try:
        preview = preview_household_catalog_identity_backfill(conn, household_id="h1")
        with pytest.raises(ValueError, match="changed"):
            apply_reviewed_household_catalog_identity_backfill(
                conn, household_id="h1", reviewed_plan_token="0" * 64,
            )
        conn.execute(text(
            "INSERT INTO household_articles VALUES ('a3','h1','p1')"
        ))
        with pytest.raises(ValueError, match="changed"):
            apply_reviewed_household_catalog_identity_backfill(
                conn, household_id="h1", reviewed_plan_token=preview["plan_token"],
            )
        assert conn.execute(text(
            "SELECT global_product_id FROM household_articles WHERE id='a1'"
        )).scalar_one() is None
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_unidentified_historical_line_blocks_partial_auto_link():
    engine, conn = _fixture()
    try:
        # One exact identity and a second receipt line without any identifier:
        # we cannot prove both refer to the same Catalogus product.
        conn.execute(text(
            "INSERT INTO receipt_table_lines VALUES ('l3','r1',NULL,NULL,FALSE)"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_lines VALUES ('b1','receipt-line:l3','a1')"
        ))
        result = preview_household_catalog_identity_backfill(
            conn, household_id="h1", include_candidates=True,
        )
        assert result["eligible"] == 0, result
        assert result["unresolved"] == 1, result
        assert result["eligible_candidates"] == [], result
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()
