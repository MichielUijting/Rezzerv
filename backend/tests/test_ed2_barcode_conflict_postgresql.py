"""Real PostgreSQL contract for exact Superuser barcode conflict correction.

Runs ONLY on a deliberately isolated *_identity_test database. Temporary tables
shadow the application schema. Always rolls back, never touches actual user data.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.ed2_barcode_conflict_resolution_service import (
    confirm_barcode_conflict_resolution, preview_barcode_conflict_resolution,
)

SOURCE = {
    "retailer_code": "Albert Heijn",
    "receipt_text": "RISOTTORIJST",
    "external_article_code": "24827",
}
ID = "receipt-table-line:risotto"
CATALOG = "8712345678906"
MANUAL = "8722800072026"
NEW = "8711111111111"


@pytest.fixture
def isolated_pg():
    url = os.environ.get("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Only isolated PostgreSQL identity database is permitted")
    parsed = make_url(url)
    if (parsed.get_backend_name() != "postgresql"
            or not str(parsed.database or "").endswith("_identity_test")):
        raise RuntimeError("No production or operator database may be used in this test")
    engine = create_engine(url)
    conn = engine.connect()
    try:
        ddl = [
            """CREATE TEMP TABLE global_products (
                id TEXT PRIMARY KEY, name TEXT, status TEXT,
                primary_gtin TEXT, brand TEXT, variant TEXT, category TEXT,
                size_value NUMERIC, size_unit TEXT, product_fingerprint TEXT,
                source TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
            )""",
            """CREATE TEMP TABLE product_identities (
                id TEXT, household_article_id TEXT, global_product_id TEXT,
                identity_type TEXT, identity_value TEXT, source TEXT,
                confidence_score NUMERIC, is_primary BOOLEAN,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )""",
            """CREATE TEMP TABLE ed2_manual_barcodes (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, gtin TEXT,
                barcode_scope TEXT, global_product_id TEXT,
                confirmed_by TEXT, confirmed_at TIMESTAMP,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )""",
            """CREATE TEMP TABLE external_article_product_links (
                id TEXT, retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                status TEXT, confirmed_by TEXT, confirmed_at TIMESTAMP,
                source_candidate_id TEXT, created_at TIMESTAMP,
                updated_at TIMESTAMP
            )""",
            """CREATE TEMP TABLE receipt_tables (
                id TEXT, household_id TEXT, store_chain TEXT,
                store_name TEXT, deleted_at TIMESTAMP
            )""",
            """CREATE TEMP TABLE receipt_table_lines (
                id TEXT, receipt_table_id TEXT, external_article_code TEXT,
                corrected_raw_label TEXT, normalized_label TEXT, raw_label TEXT,
                is_deleted BOOLEAN
            )""",
            """CREATE TEMP TABLE household_articles (
                id TEXT, household_id TEXT, global_product_id TEXT
            )""",
            """CREATE TEMP TABLE inventory (
                id TEXT, household_id TEXT, household_article_id TEXT,
                quantity NUMERIC
            )""",
            """CREATE TEMP TABLE auth_audit_log (
                id TEXT, actor_user_id TEXT, actor_type TEXT,
                household_id TEXT, support_session_id TEXT,
                action TEXT, object_type TEXT, object_id TEXT,
                old_value TEXT, new_value TEXT, reason TEXT,
                ticket_reference TEXT, created_at TEXT
            )""",
        ]
        for statement in ddl:
            conn.execute(text(statement))
        for id_, name, gtin in [
            ("catalog", "RISOTTO", CATALOG),
            ("manual", "RISOTTORIJST", MANUAL),
            ("other", "Risotto alternatieve GTIN", NEW),
        ]:
            conn.execute(text("""
                INSERT INTO global_products(id,name,status,primary_gtin)
                VALUES (:id,:name,'active',:gtin)
            """), {"id": id_, "name": name, "gtin": gtin})
            conn.execute(text("""
                INSERT INTO product_identities
                    (id,household_article_id,global_product_id,identity_type,identity_value)
                VALUES (:id,'',:product,'gtin',:value)
            """), {"id": "pi-" + id_, "product": id_, "value": gtin})
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (id,retailer_code,receipt_text_normalized,external_article_code,
                 global_product_id,status,confirmed_by,confirmed_at,created_at,updated_at)
            VALUES ('central','ah','risottorijst','24827',
                    'catalog','confirmed','historical',CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """))
        conn.execute(text("""
            INSERT INTO ed2_manual_barcodes
                (retailer_code,receipt_text_normalized,external_article_code,gtin,
                 barcode_scope,global_product_id,confirmed_by,confirmed_at,
                 created_at,updated_at)
            VALUES ('ah','risottorijst','24827',:gtin,
                    'global_candidate','manual','superuser',CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """), {"gtin": MANUAL})
        conn.execute(text("""
            INSERT INTO receipt_tables VALUES
              ('r1','h1','Albert Heijn','AH',NULL),
              ('r2','h2','Albert Heijn','AH',NULL)
        """))
        conn.execute(text("""
            INSERT INTO receipt_table_lines VALUES
              ('l1','r1','24827',NULL,NULL,'RISOTTORIJST',FALSE),
              ('l2','r2','24827',NULL,NULL,'RISOTTORIJST',FALSE)
        """))
        conn.execute(text("""
            INSERT INTO household_articles VALUES
              ('a1','h1','catalog'), ('a2','h2','manual')
        """))
        conn.execute(text("""
            INSERT INTO inventory VALUES
              ('i1','h1','a1',3), ('i2','h2','a2',5)
        """))
        yield conn
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def _rows(conn, table, order):
    return conn.execute(text("SELECT * FROM " + table + " ORDER BY " + order)).all()


@pytest.mark.parametrize("mode,other,expected,product", [
    ("keep_catalog", "", CATALOG, "catalog"),
    ("keep_manual", "", MANUAL, "manual"),
    ("use_other", NEW, NEW, "other"),
])
def test_postgresql_conflict_correction_is_atomic_and_preserves_household_data(
        isolated_pg, mode, other, expected, product):
    conn = isolated_pg
    protected = {
        table: _rows(conn, table, order)
        for table, order in [
            ("global_products", "id"),
            ("product_identities", "id"),
            ("receipt_tables", "id"),
            ("receipt_table_lines", "id"),
            ("household_articles", "id"),
            ("inventory", "id"),
        ]
    }
    pre = preview_barcode_conflict_resolution(
        conn, source=SOURCE, receipt_item_id=ID, mode=mode, new_gtin=other,
    )
    assert pre["can_confirm"] is True, pre
    assert pre["catalog_gtin"] == CATALOG and pre["old_manual_gtin"] == MANUAL
    assert conn.execute(text("SELECT COUNT(*) FROM auth_audit_log")).scalar_one() == 0
    after = confirm_barcode_conflict_resolution(
        conn, source=SOURCE, receipt_item_id=ID, mode=mode, new_gtin=other,
        preview_fingerprint=pre["preview_fingerprint"], actor_user_id="platform-superuser",
    )
    assert after == {
        "corrected": True, "mode": mode, "gtin": expected,
        "global_product_id": product, "receipt_changes": 0,
        "household_changes": 0, "stock_changes": 0,
    }
    central = conn.execute(text("""
        SELECT status FROM external_article_product_links WHERE id = 'central'
    """)).scalar_one()
    assert central == ("confirmed" if mode == "keep_catalog" else "inactive")
    saved = conn.execute(text("""
        SELECT gtin, global_product_id FROM ed2_manual_barcodes
    """)).all()
    assert saved == ([] if mode == "keep_catalog" else [(expected, product)])
    for table, order in [
        ("global_products", "id"), ("product_identities", "id"),
        ("receipt_tables", "id"), ("receipt_table_lines", "id"),
        ("household_articles", "id"), ("inventory", "id"),
    ]:
        assert _rows(conn, table, order) == protected[table]
    logs = conn.execute(text("""
        SELECT actor_type, action FROM auth_audit_log
    """)).all()
    assert logs == [("platform_user", "catalog.ed2.barcode_conflict.resolved")]
    with pytest.raises(ValueError):
        confirm_barcode_conflict_resolution(
            conn, source=SOURCE, receipt_item_id=ID, mode=mode, new_gtin=other,
            preview_fingerprint=pre["preview_fingerprint"],
            actor_user_id="platform-superuser",
        )


def test_other_household_same_code_different_receipt_name_blocks_reassignment(isolated_pg):
    conn = isolated_pg
    conn.execute(text("""
        UPDATE receipt_table_lines SET raw_label = 'AH ANDERE RIJST'
        WHERE id = 'l2'
    """))
    before_link = _rows(conn, "external_article_product_links", "id")
    before_manual = _rows(conn, "ed2_manual_barcodes", "retailer_code")
    pre = preview_barcode_conflict_resolution(
        conn, source=SOURCE, receipt_item_id=ID, mode="keep_manual",
    )
    assert not pre["can_confirm"]
    assert any("andere artikelnamen" in z for z in pre["blocked_reasons"])
    with pytest.raises(ValueError, match="Correctie"):
        confirm_barcode_conflict_resolution(
            conn, source=SOURCE, receipt_item_id=ID, mode="keep_manual",
            new_gtin="", preview_fingerprint=pre["preview_fingerprint"],
            actor_user_id="platform-superuser",
        )
    assert _rows(conn, "external_article_product_links", "id") == before_link
    assert _rows(conn, "ed2_manual_barcodes", "retailer_code") == before_manual
    assert conn.execute(text("SELECT COUNT(*) FROM auth_audit_log")).scalar_one() == 0
