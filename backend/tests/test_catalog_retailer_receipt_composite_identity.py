"""PostgreSQL regression for the PO's retailer + receipt label + receipt number identity."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.external_article_product_link_service import get_confirmed_external_article_product_link


@pytest.fixture
def identity_conn():
    url = os.getenv("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Dedicated PostgreSQL identity-test database not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_identity_test"):
        raise RuntimeError("Refusing any non-isolated PostgreSQL database")
    engine = create_engine(parsed.set(drivername="postgresql+psycopg"))
    conn = engine.connect()
    try:
        conn.execute(text("""CREATE TEMP TABLE global_products
            (id TEXT PRIMARY KEY, name TEXT, primary_gtin TEXT, status TEXT)"""))
        conn.execute(text("""CREATE TEMP TABLE product_identities
            (id TEXT, global_product_id TEXT, identity_type TEXT, identity_value TEXT)"""))
        conn.execute(text("""CREATE TEMP TABLE external_article_product_links
            (id TEXT, retailer_code TEXT, receipt_text_normalized TEXT,
             external_article_code TEXT, global_product_id TEXT, status TEXT,
             confirmed_by TEXT, confirmed_at TIMESTAMP, source_candidate_id TEXT,
             created_at TIMESTAMP, updated_at TIMESTAMP)"""))
        conn.execute(text("""INSERT INTO global_products VALUES
            ('p1','Lidl melk','8712345678906','active'),
            ('p2','Lidl soep','8712345678906','active')"""))
        conn.execute(text("""INSERT INTO external_article_product_links
            (id,retailer_code,receipt_text_normalized,external_article_code,global_product_id,status)
            VALUES
            ('l1','lidl','melk','001','p1','confirmed'),
            ('l2','lidl','melk','002','p1','confirmed'),
            ('l3','lidl','soep','001','p2','confirmed')"""))
        yield conn
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_one_receipt_description_allows_several_distinct_receipt_numbers(identity_conn):
    conn = identity_conn
    for code in ("001","002"):
        matched = resolve_catalog_identity(conn, retailer_code="Lidl",
                                            receipt_text=" Melk ", external_article_code=code)
        assert matched["status"] == "matched"
        assert matched["global_product_id"] == "p1"


def test_the_same_receipt_number_with_other_description_can_be_distinct(identity_conn):
    conn = identity_conn
    for description, product in (("melk","p1"),("soep","p2")):
        matched = resolve_catalog_identity(conn, retailer_code="Lidl",
                                            receipt_text=description, external_article_code="001")
        assert matched["status"] == "matched"
        assert matched["global_product_id"] == product
        read = get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", receipt_text=description,
            external_article_code="001")
        assert read and read["global_product_id"] == product
    # Without receipt label two competing owners cannot be chosen at random.
    assert resolve_catalog_identity(conn, retailer_code="Lidl",
                                    external_article_code="001")["status"] == "conflict"


def test_two_catalogus_products_for_one_complete_receipt_identity_fail_closed(identity_conn):
    conn = identity_conn
    conn.execute(text("""INSERT INTO external_article_product_links
        (id,retailer_code,receipt_text_normalized,external_article_code,global_product_id,status)
        VALUES ('l4','lidl','melk','001','p2','confirmed')"""))
    match = resolve_catalog_identity(conn, retailer_code="Lidl",
                                     receipt_text="melk", external_article_code="001")
    assert match["status"] == "conflict"
    assert match["global_product_id"] is None
