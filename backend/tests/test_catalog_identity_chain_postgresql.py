"""PostgreSQL identity chain: Kassa receipt -> Uitpakken -> household -> stock.

Real production identity confirmation, reader and repair services run against
isolated temporary PostgreSQL tables. This is a data-chain regression, not
a browser end-to-end test of the actual Bijna op calculation.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.catalog_identity_confirmation_service import confirm_scanned_retailer_identity
from app.services.almost_out_group_service import load_groups, load_group_projection
from app.services.catalog_identity_live_repair_service import repair_household_articles_for_confirmed_store_code
from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.external_article_product_link_service import get_confirmed_external_article_product_link

GTIN = "8712345678906"


def _chain():
    url = os.environ.get("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Isolated PostgreSQL test database not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_identity_test"):
        raise RuntimeError("Refusing to write to a non-isolated database")
    engine = create_engine(url)
    conn = engine.connect()
    for sql in (
        "CREATE TEMP TABLE global_products (id TEXT PRIMARY KEY, name TEXT, primary_gtin TEXT, status TEXT, size_value NUMERIC, size_unit TEXT, variant TEXT)",
        "CREATE TEMP TABLE product_identities (id TEXT, global_product_id TEXT, identity_type TEXT, identity_value TEXT)",
        """CREATE TEMP TABLE external_article_product_links (
            id TEXT, retailer_code TEXT, receipt_text_normalized TEXT,
            external_article_code TEXT, global_product_id TEXT,
            status TEXT, confirmed_by TEXT, confirmed_at TIMESTAMP,
            source_candidate_id TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
        )""",
        "CREATE TEMP TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT, status TEXT)",
        "CREATE TEMP TABLE receipt_tables (id TEXT PRIMARY KEY, household_id TEXT, store_chain TEXT, store_name TEXT, deleted_at TIMESTAMP)",
        """CREATE TEMP TABLE receipt_table_lines (
            id TEXT PRIMARY KEY, receipt_table_id TEXT, barcode TEXT,
            external_article_code TEXT, is_deleted BOOLEAN,
            line_role TEXT, inventory_eligible INTEGER
        )""",
        "CREATE TEMP TABLE purchase_import_batches (id TEXT PRIMARY KEY, household_id TEXT, source_reference TEXT, source_type TEXT)",
        "CREATE TEMP TABLE purchase_import_lines (batch_id TEXT, external_line_ref TEXT, matched_household_article_id TEXT)",
        "CREATE TEMP TABLE inventory (id TEXT, household_id TEXT, household_article_id TEXT, quantity NUMERIC, naam TEXT, aantal NUMERIC, space_id TEXT, sublocation_id TEXT, status TEXT)",
        "CREATE TEMP TABLE inventory_events (id TEXT, household_id TEXT, household_article_id TEXT, delta NUMERIC, article_id TEXT, quantity NUMERIC, created_at TIMESTAMP)",
        "CREATE TEMP TABLE almost_out_inputs (household_id TEXT, household_article_id TEXT, threshold NUMERIC)",
        "CREATE TEMP TABLE global_product_gpc_bricks (global_product_id TEXT, brick_code TEXT)",
        "CREATE TEMP TABLE global_product_consumption_profiles (global_product_id TEXT, facts_json TEXT)",
        "CREATE TEMP TABLE article_synonym_links (left_product_id TEXT, right_product_id TEXT)",
        "CREATE TEMP TABLE spaces (id TEXT, household_id TEXT, naam TEXT)",
        "CREATE TEMP TABLE sublocations (id TEXT, space_id TEXT, naam TEXT)",
    ):
        conn.execute(text(sql))
    conn.execute(text("INSERT INTO global_products (id,name,primary_gtin,status) VALUES ('p1','Lidl melk',:gtin,'active')"), {"gtin": GTIN})
    conn.execute(text("INSERT INTO product_identities VALUES ('pi1','p1','gtin',:gtin)"), {"gtin": GTIN})
    conn.execute(text("INSERT INTO household_articles (id,household_id,global_product_id) VALUES ('a1','h1',NULL),('a2','h2',NULL)"))
    conn.execute(text("""
        INSERT INTO receipt_tables VALUES
        ('r1','h1','Lidl Nederland GmbH','Lidl',NULL),
        ('r2','h2','Lidl','Lidl',NULL)
    """))
    conn.execute(text("""
        INSERT INTO receipt_table_lines VALUES
        ('l1','r1',NULL,'0082346',FALSE,'product',1),
        ('l2','r2',NULL,'0082346',FALSE,'product',1)
    """))
    conn.execute(text("""
        INSERT INTO purchase_import_batches VALUES
        ('b1','h1','receipt:r1','receipt'),
        ('b2','h2','receipt:r2','receipt')
    """))
    conn.execute(text("""
        INSERT INTO purchase_import_lines VALUES
        ('b1','receipt-line:l1','a1'),
        ('b2','receipt-line:l2','a2')
    """))
    conn.execute(text("INSERT INTO inventory (id,household_id,household_article_id,quantity,naam,aantal,status) VALUES ('s1','h1','a1',2,'Lidl melk',2,'active'),('s2','h2','a2',3,'Lidl melk',3,'active')"))
    conn.execute(text("INSERT INTO inventory_events (id,household_id,household_article_id,delta,article_id,quantity,created_at) VALUES ('e1','h1','a1',2,'a1',2,CURRENT_TIMESTAMP),('e2','h2','a2',3,'a2',3,CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO almost_out_inputs VALUES ('h1','a1',4),('h2','a2',1)"))
    return engine, conn


def _snap(conn, table):
    return conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()


def test_confirmed_barcode_flows_through_exact_receipt_unpack_household_and_stock():
    engine, conn = _chain()
    try:
        stock_before = _snap(conn, "inventory")
        events_before = _snap(conn, "inventory_events")
        signals_before = conn.execute(text("""
            SELECT household_id,household_article_id,threshold
            FROM almost_out_inputs ORDER BY household_id
        """)).all()

        # Kassa: store-specific code alone is not yet enough to link.
        before = resolve_catalog_identity(conn, retailer_code="lidl",
                                          external_article_code="0082346")
        assert before["status"] == "not_found", before

        # Artikelbeheer: user confirms a scanned, unique Catalogus GTIN.
        confirmation = confirm_scanned_retailer_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            scanned_gtin=GTIN, confirmed_by="user-test",
        )
        assert confirmation["status"] == "confirmed"
        assert confirmation["global_product_id"] == "p1"

        # Kassa and Uitpakken resolve precisely the same retailer/code identity.
        source = conn.execute(text("""
            SELECT rtl.external_article_code, rtl.barcode,
                   pil.matched_household_article_id
            FROM receipt_table_lines rtl
            JOIN purchase_import_lines pil
              ON pil.external_line_ref = 'receipt-line:' || rtl.id
            WHERE rtl.id='l1'
        """)).mappings().one()
        assert source["external_article_code"] == "0082346"
        assert source["barcode"] is None
        assert source["matched_household_article_id"] == "a1"
        receipt_identity = resolve_catalog_identity(conn, retailer_code="Lidl Nederland GmbH",
                                                     external_article_code=source["external_article_code"])
        assert receipt_identity["global_product_id"] == "p1"
        operational = get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl Nederland GmbH",
            external_article_code="0082346",
        )
        assert operational and operational["global_product_id"] == "p1"

        # Historical link for current household; never for other household.
        repair = repair_household_articles_for_confirmed_store_code(
            conn, household_id="h1", retailer_code="lidl",
            external_article_code="0082346", global_product_id="p1",
        )
        assert repair["updated"] == 1, repair
        assert conn.execute(text("SELECT global_product_id FROM household_articles WHERE id='a1'")).scalar_one() == "p1"
        assert conn.execute(text("SELECT global_product_id FROM household_articles WHERE id='a2'")).scalar_one() is None

        # Voorraad and Bijna op are projections through the SAME household
        # article ID. They must not be duplicated or quantity-adjusted.
        joined = conn.execute(text("""
            SELECT inv.household_article_id, ha.global_product_id,
                   inv.quantity, sig.threshold, (inv.quantity < sig.threshold) AS below
            FROM inventory inv
            JOIN household_articles ha ON ha.id = inv.household_article_id
                                      AND ha.household_id = inv.household_id
            JOIN almost_out_inputs sig ON sig.household_article_id = ha.id
                                      AND sig.household_id = ha.household_id
            WHERE inv.household_id='h1'
        """)).mappings().one()
        assert joined["household_article_id"] == "a1"
        assert joined["global_product_id"] == "p1"
        assert joined["quantity"] == 2
        assert joined["below"] is True
        # Exercise the ACTUAL Bijna op grouping and inventory/event projection
        # rather than only comparing an invented threshold view.
        groups = load_groups(conn, "h1", [{"id": "a1", "name": "Lidl melk"}], {})
        assert len(groups) == 1
        assert groups[0]["key"] == ("product", "p1")
        projected = load_group_projection(conn, "h1", groups[0])
        assert projected["member_article_ids"] == ["a1"]
        assert projected["member_data_inconsistent"] is False
        assert len(projected["inventory_rows"]) == 1
        assert projected["inventory_rows"][0]["quantity"] == 2
        assert len(projected["event_rows"]) == 1
        assert projected["event_rows"][0]["quantity"] == 2
        assert stock_before == _snap(conn, "inventory")
        assert events_before == _snap(conn, "inventory_events")
        assert signals_before == conn.execute(text("""
            SELECT household_id,household_article_id,threshold
            FROM almost_out_inputs ORDER BY household_id
        """)).all()

        repeated = confirm_scanned_retailer_identity(
            conn, retailer_code="lidl", external_article_code="0082346",
            scanned_gtin=GTIN, confirmed_by="user-test",
        )
        assert repeated["status"] == "already_confirmed"
        assert repair_household_articles_for_confirmed_store_code(
            conn, household_id="h1", retailer_code="lidl",
            external_article_code="0082346", global_product_id="p1",
        )["updated"] == 0
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_conflicting_receipt_line_blocks_historical_repair_without_stock_changes():
    engine, conn = _chain()
    try:
        confirm_scanned_retailer_identity(
            conn, retailer_code="lidl", external_article_code="0082346",
            scanned_gtin=GTIN, confirmed_by="user-test",
        )
        conn.execute(text("""
            INSERT INTO receipt_table_lines VALUES
            ('l3','r1',NULL,'other-code',FALSE,'product',1)
        """))
        conn.execute(text("""
            INSERT INTO purchase_import_lines VALUES ('b1','receipt-line:l3','a1')
        """))
        stock_before = _snap(conn, "inventory")
        events_before = _snap(conn, "inventory_events")
        result = repair_household_articles_for_confirmed_store_code(
            conn, household_id="h1", retailer_code="lidl",
            external_article_code="0082346", global_product_id="p1",
        )
        assert result["updated"] == 0, result
        assert conn.execute(text("SELECT global_product_id FROM household_articles WHERE id='a1'")).scalar_one() is None
        assert stock_before == _snap(conn, "inventory")
        assert events_before == _snap(conn, "inventory_events")
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()
