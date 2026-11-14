"""Catalogus identity must be exact, unique and classification-independent."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.services.catalog_identity_resolution_service import resolve_catalog_identity


def _conn():
    url = os.environ.get("INHUIS_IDENTITY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Dedicated PostgreSQL identity test database not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_identity_test"):
        raise RuntimeError("Refusing non-isolated identity test database")
    engine = create_engine(url)
    conn = engine.connect()
    conn.execute(text("CREATE TEMP TABLE global_products (id TEXT PRIMARY KEY, primary_gtin TEXT, status TEXT, name TEXT)"))
    conn.execute(text("CREATE TEMP TABLE product_identities (id TEXT, global_product_id TEXT, identity_type TEXT, identity_value TEXT)"))
    conn.execute(text("CREATE TEMP TABLE external_article_product_links (global_product_id TEXT, retailer_code TEXT, external_article_code TEXT, status TEXT, confirmed_by TEXT DEFAULT NULL, id TEXT, receipt_text_normalized TEXT, confirmed_at TIMESTAMP, source_candidate_id TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)"))
    conn.execute(text("INSERT INTO global_products (id, primary_gtin, status) VALUES ('p1', '8712345678906', 'active'), ('p2', NULL, 'active'), ('p3', NULL, 'inactive')"))
    return engine, conn


def test_confirmed_store_code_matches_without_classification():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p1','lidl','abc-123','confirmed')"))
        result = resolve_catalog_identity(conn, retailer_code="Lidl", external_article_code="ABC-123")
        assert result["status"] == "matched", result
        assert result["global_product_id"] == "p1"
    finally:
        conn.close()
        engine.dispose()


def test_pending_classification_is_not_confirmation():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p1','lidl','abc-123','classification_pending')"))
        assert resolve_catalog_identity(conn, retailer_code="lidl", external_article_code="ABC-123")["status"] == "not_found"
    finally:
        conn.close()
        engine.dispose()


def test_ambiguous_code_fails_closed():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p1','lidl','abc-123','confirmed')"))
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p2','lidl','abc-123','confirmed')"))
        assert resolve_catalog_identity(conn, retailer_code="lidl", external_article_code="ABC-123")["status"] == "conflict"
    finally:
        conn.close()
        engine.dispose()


def test_same_code_in_other_shop_does_not_match():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p1','lidl','abc-123','confirmed')"))
        assert resolve_catalog_identity(conn, retailer_code="jumbo", external_article_code="ABC-123")["status"] == "not_found"
        assert resolve_catalog_identity(conn, external_article_code="ABC-123")["status"] == "retailer_required"
    finally:
        conn.close()
        engine.dispose()


def test_gtin_and_retailer_identity_must_agree():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p2','lidl','abc-123','confirmed')"))
        result = resolve_catalog_identity(conn, gtin="8712345678906", retailer_code="lidl", external_article_code="ABC-123")
        assert result["status"] == "conflict", result
        assert result["global_product_id"] is None
    finally:
        conn.close()
        engine.dispose()


def test_inactive_products_are_not_candidates():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO external_article_product_links (global_product_id,retailer_code,external_article_code,status) VALUES ('p3','lidl','abc-123','confirmed')"))
        assert resolve_catalog_identity(conn, retailer_code="lidl", external_article_code="ABC-123")["status"] == "not_found"
    finally:
        conn.close()
        engine.dispose()


def test_unknown_or_invalid_gtin_cannot_be_assigned():
    engine, conn = _conn()
    try:
        assert resolve_catalog_identity(conn, gtin="0000")["status"] == "invalid_gtin"
        assert resolve_catalog_identity(conn)["status"] == "no_identity"
    finally:
        conn.close()
        engine.dispose()


def test_user_confirmed_identity_can_be_pending_classification():
    engine, conn = _conn()
    try:
        conn.execute(text("INSERT INTO product_identities VALUES ('i1','p1','gtin','8712345678906')"))
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status,confirmed_by)
            VALUES ('p1','lidl','abc-123','classification_pending','external_databases_off_pending_gpc')
        """))
        result = resolve_catalog_identity(conn, retailer_code="lidl", external_article_code="ABC-123")
        assert result["status"] == "matched", result
        assert result["global_product_id"] == "p1"
    finally:
        conn.close()
        engine.dispose()


def test_scanned_gtin_confirmation_creates_idempotent_store_identity_without_classification():
    from app.services.catalog_identity_confirmation_service import (
        confirm_scanned_retailer_identity,
    )
    engine, conn = _conn()
    try:
        result = confirm_scanned_retailer_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            scanned_gtin="8712345678906", confirmed_by="authenticated-user-test",
        )
        assert result["status"] == "confirmed", result
        assert result["changes"] == 1
        assert resolve_catalog_identity(conn, retailer_code="lidl",
                                        external_article_code="0082346")["global_product_id"] == "p1"
        again = confirm_scanned_retailer_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            scanned_gtin="8712345678906", confirmed_by="authenticated-user-test",
        )
        assert again["status"] == "already_confirmed"
        assert again["changes"] == 0
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_scanned_gtin_confirmation_rejects_unverified_and_conflicting_code():
    from app.services.catalog_identity_confirmation_service import (
        confirm_scanned_retailer_identity,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status)
            VALUES ('p2','lidl','0082346','confirmed')
        """))
        with pytest.raises(ValueError, match="tegenstrijdige"):
            confirm_scanned_retailer_identity(
                conn, retailer_code="lidl", external_article_code="0082346",
                scanned_gtin="8712345678906", confirmed_by="tester",
            )
        with pytest.raises(ValueError, match="geldige barcode"):
            confirm_scanned_retailer_identity(
                conn, retailer_code="lidl", external_article_code="0083006",
                scanned_gtin="8712345678900", confirmed_by="tester",
            )
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_ah_chain_alias_is_same_retailer_but_never_other_store():
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status)
            VALUES ('p1','albert-heijn','n001','confirmed')
        """))
        assert resolve_catalog_identity(
            conn, retailer_code="AH", external_article_code="N001",
        )["global_product_id"] == "p1"
        assert resolve_catalog_identity(
            conn, retailer_code="Jumbo", external_article_code="N001",
        )["status"] == "not_found"
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status)
            VALUES ('p2','ah','n001','confirmed')
        """))
        assert resolve_catalog_identity(
            conn, retailer_code="Albert Heijn", external_article_code="n001",
        )["status"] == "conflict"
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_confirmed_retailer_alias_conflict_blocks_scanned_identity():
    from app.services.catalog_identity_confirmation_service import (
        confirm_scanned_retailer_identity,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status)
            VALUES ('p2','lidl-nederland-gmbh','0082346','confirmed')
        """))
        with pytest.raises(ValueError, match="tegenstrijdige"):
            confirm_scanned_retailer_identity(
                conn, retailer_code="Lidl", external_article_code="0082346",
                scanned_gtin="8712345678906", confirmed_by="tester",
            )
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_operational_reader_accepts_proven_code_without_any_gpc_classification():
    from app.services.external_article_product_link_service import (
        get_confirmed_external_article_product_link,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status)
            VALUES ('p1','lidl-nederland-gmbh','abc-123','confirmed')
        """))
        result = get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", external_article_code="ABC-123",
        )
        assert result and result["global_product_id"] == "p1", result
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_operational_reader_requires_off_pending_gtin_evidence():
    from app.services.external_article_product_link_service import (
        get_confirmed_external_article_product_link,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,status,confirmed_by)
            VALUES ('p1','lidl','abc-123','classification_pending',
                    'external_databases_off_pending_gpc')
        """))
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="lidl", external_article_code="abc-123",
        ) is None
        conn.execute(text(
            "INSERT INTO product_identities VALUES ('i1','p1','gtin','8712345678906')"
        ))
        matched = get_confirmed_external_article_product_link(
            conn, retailer_code="lidl", external_article_code="abc-123",
        )
        assert matched and matched["global_product_id"] == "p1", matched
        assert matched["status"] == "classification_pending"
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_operational_reader_never_falls_back_to_name_for_unknown_store_code():
    from app.services.external_article_product_link_service import (
        get_confirmed_external_article_product_link,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (global_product_id,retailer_code,external_article_code,
                 receipt_text_normalized,status)
            VALUES ('p1','lidl','abc-123','the product','confirmed')
        """))
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="lidl", external_article_code="unknown",
            receipt_text="the product",
        ) is None
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()



def test_exact_approved_receipt_tuple_reuses_identity_without_barcode():
    engine, conn = _conn()
    try:
        conn.execute(text("""
            CREATE TEMP TABLE ed2_receipt_family_links (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                confirmed_by TEXT
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            INSERT INTO ed2_receipt_family_links
              VALUES ('lidl', 'courgette groen', '0082346', 'p1', 'superuser')
        """))
        match = resolve_catalog_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette groen",
        )
        assert match["status"] == "matched", match
        assert match["global_product_id"] == "p1"
        assert "confirmed_receipt_tuple" in match["evidence"]
        assert resolve_catalog_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette geel",
        )["status"] == "not_found"
        assert resolve_catalog_identity(
            conn, retailer_code="Jumbo", external_article_code="0082346",
            receipt_text="Courgette groen",
        )["status"] == "not_found"
        assert resolve_catalog_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
        )["status"] == "not_found"
        assert resolve_catalog_identity(
            conn, retailer_code="Lidl", external_article_code="",
            receipt_text="Courgette groen",
        )["status"] == "no_identity"
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()


def test_confirmed_receipt_tuple_never_overrides_conflicting_gtin_or_code():
    engine, conn = _conn()
    try:
        conn.execute(text("""
            CREATE TEMP TABLE ed2_receipt_family_links (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                confirmed_by TEXT
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            INSERT INTO ed2_receipt_family_links
              VALUES ('lidl', 'courgette groen', '0082346', 'p2', 'superuser')
        """))
        conn.execute(text("""
            INSERT INTO external_article_product_links
              (global_product_id, retailer_code, external_article_code, status)
            VALUES ('p1','lidl','0082346','confirmed')
        """))
        claim = resolve_catalog_identity(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette groen",
        )
        assert claim["status"] == "conflict"
        assert claim["global_product_id"] is None
        conn.execute(text("DELETE FROM external_article_product_links"))
        claim = resolve_catalog_identity(
            conn, gtin="8712345678906", retailer_code="Lidl",
            external_article_code="0082346", receipt_text="Courgette groen",
        )
        assert claim["status"] == "conflict"
        assert claim["global_product_id"] is None
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()



def test_operational_reader_reuses_exact_barcode_free_receipt_without_fabricated_gtin():
    from app.services.external_article_product_link_service import (
        get_confirmed_external_article_product_link,
    )
    engine, conn = _conn()
    try:
        conn.execute(text("""
            CREATE TEMP TABLE ed2_receipt_family_links (
                retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                confirmed_by TEXT, confirmed_at TIMESTAMP
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            INSERT INTO ed2_receipt_family_links
              VALUES ('lidl', 'courgette groen', '0082346', 'p1',
                      'frontteam-authorized', CURRENT_TIMESTAMP)
        """))
        result = get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette groen",
        )
        assert result and result["global_product_id"] == "p1"
        assert result["source"] == "confirmed_receipt_tuple"
        assert result["primary_gtin"] == ""
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette geel",
        ) is None
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="Jumbo", external_article_code="0082346",
            receipt_text="Courgette groen",
        ) is None
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", external_article_code="0082346",
        ) is None
        conn.execute(text("""
            INSERT INTO external_article_product_links
              (global_product_id, retailer_code, external_article_code, status)
            VALUES ('p2', 'lidl', '0082346', 'confirmed')
        """))
        assert get_confirmed_external_article_product_link(
            conn, retailer_code="Lidl", external_article_code="0082346",
            receipt_text="Courgette groen",
        ) is None
    finally:
        conn.rollback()
        conn.close()
        engine.dispose()
