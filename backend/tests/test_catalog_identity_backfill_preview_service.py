"""Exact historical receipt lineage must be dry-run and conflict-safe."""
from sqlalchemy import create_engine, text

from app.services.catalog_identity_backfill_preview_service import (
    preview_household_catalog_identity_backfill,
)


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    conn = engine.connect()
    statements = [
        "CREATE TABLE global_products (id TEXT PRIMARY KEY, primary_gtin TEXT, status TEXT)",
        "CREATE TABLE product_identities (id TEXT, global_product_id TEXT, identity_type TEXT, identity_value TEXT)",
        "CREATE TABLE external_article_product_links (global_product_id TEXT, retailer_code TEXT, external_article_code TEXT, status TEXT)",
        "CREATE TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT)",
        "CREATE TABLE receipt_tables (id TEXT PRIMARY KEY, household_id TEXT, store_name TEXT)",
        "CREATE TABLE receipt_table_lines (id TEXT PRIMARY KEY, receipt_table_id TEXT, barcode TEXT, external_article_code TEXT, is_deleted BOOLEAN)",
        "CREATE TABLE purchase_import_batches (id TEXT PRIMARY KEY, household_id TEXT, source_reference TEXT, source_type TEXT)",
        "CREATE TABLE purchase_import_lines (batch_id TEXT, external_line_ref TEXT, matched_household_article_id TEXT)",
    ]
    for sql in statements:
        conn.execute(text(sql))
    conn.execute(text("INSERT INTO global_products VALUES ('p1', NULL, 'active')"))
    conn.execute(text("INSERT INTO external_article_product_links VALUES ('p1','lidl','code1','confirmed')"))
    conn.execute(text("INSERT INTO household_articles VALUES ('a1','h1',NULL), ('a2','h2',NULL)"))
    conn.execute(text("INSERT INTO receipt_tables VALUES ('r1','h1','lidl'), ('r2','h2','lidl')"))
    conn.execute(text("INSERT INTO receipt_table_lines VALUES ('l1','r1',NULL,'code1',0), ('l2','r2',NULL,'code1',0)"))
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
