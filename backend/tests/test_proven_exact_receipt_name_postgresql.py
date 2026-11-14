"""Real PostgreSQL tuple / audit persistence; isolated TEMP tables only.

Mandatory environment guard. Never write to the operator's actual database.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.proven_exact_receipt_name_service import _persist_exact_name_match


def _isolated_connection():
    url = os.environ.get("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Isolated PostgreSQL identity DB not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_identity_test"):
        raise RuntimeError("No real Inhuis user database may be used for this test")
    engine = create_engine(url)
    conn = engine.connect()
    return engine, conn


def test_exact_name_write_has_no_gtin_synonym_or_household_side_effects():
    engine, conn = _isolated_connection()
    try:
        conn.execute(text("""
            CREATE TEMP TABLE global_products (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, name TEXT, primary_gtin TEXT
            )
        """))
        conn.execute(text("""
            CREATE TEMP TABLE ed2_receipt_family_links (
                retailer_code TEXT NOT NULL, receipt_text_normalized TEXT NOT NULL,
                external_article_code TEXT NOT NULL, global_product_id TEXT NOT NULL,
                match_mode TEXT NOT NULL, confirmed_by TEXT NOT NULL,
                confirmed_at TIMESTAMP NOT NULL,
                PRIMARY KEY (retailer_code, receipt_text_normalized, external_article_code)
            )
        """))
        conn.execute(text("""
            CREATE TEMP TABLE ed2_manual_barcodes (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, gtin TEXT
            )
        """))
        conn.execute(text("""
            CREATE TEMP TABLE external_article_product_links (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TEMP TABLE auth_audit_log (
                id TEXT, actor_user_id TEXT, actor_type TEXT, household_id TEXT,
                support_session_id TEXT, action TEXT, object_type TEXT,
                object_id TEXT, old_value TEXT, new_value TEXT, reason TEXT,
                ticket_reference TEXT, created_at TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO global_products VALUES
            ('milk', 'active', 'Halfvolle melk', '8712345678906'),
            ('deleted', 'deleted', 'Historisch product', NULL)
        """))
        before = conn.execute(text("SELECT id, name, primary_gtin FROM global_products ORDER BY id")).all()
        arguments = dict(
            source_key=("jumbo", "halfvolle melk", ""),
            product_id="milk",
            witness={"retailer": "ah", "receipt_article_number": "21003"},
            actor_id="platform-frontteam",
        )
        assert _persist_exact_name_match(conn, **arguments) is True
        stored = conn.execute(text("""
            SELECT retailer_code, receipt_text_normalized, external_article_code,
                   global_product_id, match_mode, confirmed_by
            FROM ed2_receipt_family_links
        """)).one()
        assert tuple(stored) == (
            "jumbo", "halfvolle melk", "", "milk", "same_product", "platform-frontteam")
        assert _persist_exact_name_match(conn, **arguments) is False
        assert conn.execute(text("SELECT count(*) FROM ed2_receipt_family_links")).scalar_one() == 1
        audit = conn.execute(text("""
            SELECT action, reason, new_value FROM auth_audit_log
        """)).mappings().one()
        assert audit["action"] == "catalog.ed2.proven_receipt_name.confirmed"
        assert audit["reason"] == "automatic_confirmed_receipt_name_v2"
        assert '"witness_article_number": "21003"' in audit["new_value"]
        assert before == conn.execute(text(
            "SELECT id, name, primary_gtin FROM global_products ORDER BY id")).all()
        assert conn.execute(text("""
            SELECT count(*) FROM ed2_receipt_family_links WHERE match_mode='synonym_variant'
        """)).scalar_one() == 0

        with pytest.raises(ValueError, match="niet meer actief"):
            _persist_exact_name_match(
                conn, source_key=("lidl", "historisch product", ""),
                product_id="deleted", witness=arguments["witness"],
                actor_id="platform-frontteam")

        conn.execute(text("""
            INSERT INTO ed2_manual_barcodes VALUES ('plus','halfvolle melk','','8712345000001')
        """))
        with pytest.raises(ValueError, match="bewaarde barcode"):
            _persist_exact_name_match(
                conn, source_key=("plus", "halfvolle melk", ""),
                product_id="milk", witness=arguments["witness"],
                actor_id="platform-frontteam")
        conn.execute(text("""
            INSERT INTO external_article_product_links
            VALUES ('lidl', 'halfvolle melk', '', 'other', 'classification_pending')
        """))
        with pytest.raises(ValueError, match="wachtende koppeling"):
            _persist_exact_name_match(
                conn, source_key=("lidl", "halfvolle melk", ""),
                product_id="milk", witness=arguments["witness"],
                actor_id="platform-frontteam")
        assert conn.execute(text("SELECT count(*) FROM ed2_receipt_family_links")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM auth_audit_log")).scalar_one() == 1
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()
