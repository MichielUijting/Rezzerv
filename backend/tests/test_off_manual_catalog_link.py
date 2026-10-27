"""Fail-closed PO-contracttests voor handmatig OFF zoeken en bevestigen."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import off_manual_catalog_link_service as linker
from app.services import off_search_service as search
from app.services.external_database_route_authorization import required_external_database_permission

GTIN = "8718452504435"
RECEIPT = "purchase-import-line:test-line"


def product(brick=""):
    return {
        "gtin": GTIN,
        "product_name": "Halfvolle melk",
        "brand": "Jumbo",
        "quantity": "1 l",
        "explicit_gpc_brick_code": brick,
    }


def _mock_db():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.first.return_value = None
    return db


def test_link_route_is_a_write_permission_not_an_off_search_permission():
    assert required_external_database_permission(
        "POST", "/api/external-databases/off/link-selected"
    ) == "platform.external_products.link_existing"


def test_manual_search_scores_article_terms_not_just_retailer_brand():
    item = {
        "receipt_item_id": RECEIPT,
        "retailer_code": "ah",
        "receipt_line_text": "Aardbeien Albert Heijn",
        "quantity_label": "",
    }
    assert search._manual_relevance_query("Aardbeien Albert Heijn", "ah") == "aardbeien"
    with patch.object(search, "_query_off", return_value=([
        {"code": "8718452504435", "product_name": "Nederlandse aardbeien", "brands": "Albert Heijn"},
        {"code": "8718452474356", "product_name": "Viande hachée Albert Heijn", "brands": "Albert Heijn"},
    ], "test-provider")):
        result = search.search_off_candidates_for_item(
            {"mode": "manual", "query": "Aardbeien Albert Heijn", "limit": 20}, item
        )
    assert len(result["results"]) == 1
    assert result["results"][0]["product_name"] == "Nederlandse aardbeien"
    assert result["results"][0]["score"] > 0
    from app.services.off_manual_search_proof import verify_manual_off_proof
    candidate = result["results"][0]
    signed = candidate["selection_proof"]
    assert signed and signed != candidate["gtin"]
    assert verify_manual_off_proof(
        signed, receipt_item_id=RECEIPT, gtin=candidate["gtin"]
    )["product_name"] == "Nederlandse aardbeien"
    assert result["mutated"] is False


def test_invalid_barcode_fails_before_off_or_database_access():
    with patch.object(linker, "verify_manual_off_proof") as verify, patch.object(linker.engine, "begin") as begin:
        with pytest.raises(ValueError, match="geldige"):
            linker.confirm_selected_off_catalog_product({"receipt_item_id": RECEIPT, "gtin": "123"})
        verify.assert_not_called()
        begin.assert_not_called()


def test_off_identity_mismatch_fails_before_mutation():
    with patch.object(linker, "verify_manual_off_proof", side_effect=ValueError("OFF-productidentiteit klopt niet")) as verify, patch.object(linker.engine, "begin") as begin:
        with pytest.raises(ValueError, match="identiteit"):
            linker.confirm_selected_off_catalog_product({"receipt_item_id": RECEIPT, "gtin": GTIN})
        begin.assert_not_called()


def test_existing_classified_catalog_article_uses_canonical_link():
    db = _mock_db()
    db.execute.return_value.mappings.return_value.first.return_value = {"id": "existing-product"}
    with (
        patch.object(linker, "verify_manual_off_proof", return_value=product()),
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "jumbo", "receipt_text": "Halfvolle melk"
        }),
        patch.object(linker, "assert_external_product_identity_compatible") as identity,
        patch.object(linker, "_complete_global_product_link_data", return_value={
            "complete": True, "primary_gtin": GTIN,
        }),
        patch.object(linker, "confirm_external_article_for_receipt_item", return_value={"status": "confirmed", "global_product_id": "existing-product"}) as confirm,
        patch.object(linker, "link_off_product_with_product_type") as create,
    ):
        begin.return_value.__enter__.return_value = db
        result = linker.confirm_selected_off_catalog_product({"receipt_item_id": RECEIPT, "gtin": GTIN})
    assert result["linked"] is True and result["global_product_id"] == "existing-product"
    assert result["creates_inventory_event"] is False
    confirm.assert_called_once()
    identity.assert_called_once()
    create.assert_not_called()


def test_missing_gpc_is_rejected_without_catalog_mutation():
    db = _mock_db()
    with (
        patch.object(linker, "verify_manual_off_proof", return_value=product()),
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "jumbo", "receipt_text": "Halfvolle melk"
        }),
        patch.object(linker, "assert_external_product_identity_compatible"),
        patch.object(linker, "link_off_product_with_product_type") as write,
    ):
        begin.return_value.__enter__.return_value = db
        with pytest.raises(ValueError, match="GS1 GPC"):
            linker.confirm_selected_off_catalog_product({"receipt_item_id": RECEIPT, "gtin": GTIN})
        write.assert_not_called()


def test_verified_off_product_and_gpc_are_sent_to_existing_atomic_domain_service():
    db = _mock_db()
    with (
        patch.object(linker, "verify_manual_off_proof", return_value=product("10000001")),
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "jumbo", "receipt_text": "Halfvolle melk"
        }),
        patch.object(linker, "assert_external_product_identity_compatible"),
        patch.object(linker, "link_off_product_with_product_type", return_value={
            "ok": True, "linked": True, "global_product": {"id": "new-catalog"},
        }) as write,
    ):
        begin.return_value.__enter__.return_value = db
        result = linker.confirm_selected_off_catalog_product({
            "receipt_item_id": RECEIPT, "gtin": GTIN,
            "product_name": "VERVALSTE NAAM", "product_type_assignment": {"product_type_id": "fake"},
        })
    assert result["linked"] and result["global_product_id"] == "new-catalog"
    assert write.call_args.kwargs["off_product"]["product_name"] == "Halfvolle melk"
    assert write.call_args.kwargs["product_type_assignment"]["product_type_id"] == "gpc:10000001"


def test_manual_proof_is_signed_bounded_and_has_no_second_OFF_call():
    from app.services.off_manual_search_proof import (
        issue_manual_off_proof, verify_manual_off_proof,
    )
    ticket = issue_manual_off_proof(RECEIPT, product("10000001"))
    assert ticket and "." in ticket
    assert verify_manual_off_proof(ticket, receipt_item_id=RECEIPT, gtin=GTIN)["product_name"] == "Halfvolle melk"
    with pytest.raises(ValueError):
        verify_manual_off_proof(ticket, receipt_item_id="purchase-import-line:another-line", gtin=GTIN)
    with pytest.raises(ValueError):
        verify_manual_off_proof(ticket, receipt_item_id=RECEIPT, gtin="7613037010367")
    with pytest.raises(ValueError):
        verify_manual_off_proof(ticket[:-3] + "abc", receipt_item_id=RECEIPT, gtin=GTIN)
    with pytest.raises(ValueError):
        verify_manual_off_proof("", receipt_item_id=RECEIPT, gtin=GTIN)


def test_proof_expiry_and_untrusted_fields_are_rejected():
    from app.services import off_manual_search_proof as proof
    with patch.object(proof.time, "time", return_value=1000):
        ticket = proof.issue_manual_off_proof(RECEIPT, product())
    with patch.object(proof.time, "time", return_value=1602):
        with pytest.raises(ValueError, match="verlopen"):
            proof.verify_manual_off_proof(ticket, receipt_item_id=RECEIPT, gtin=GTIN)
    assert proof.issue_manual_off_proof(RECEIPT, {"gtin": "invalid", "product_name": "X"}) == ""


def test_official_ham_gpc_bridge_is_exact_and_verified_against_bundled_gs1():
    from app.services.automatic_product_type_service import official_bricks
    # GS1 cured pork ham: official Brick 10005781; both known Dutch name
    # and current official reference are required.
    assert "10005781" in official_bricks()
    assert linker._verified_official_gpc_for_exact_name({
        "product_name": "Achterham", "brand": "Zwagerman (Lidl)"
    }) == "10005781"
    assert linker._verified_official_gpc_for_exact_name({"product_name": "Kalkoenham"}) == ""
    assert linker._verified_official_gpc_for_exact_name({"product_name": "Onbekend product"}) == ""
    with patch.object(linker, "official_bricks", return_value={}):
        assert linker._verified_official_gpc_for_exact_name({"product_name": "Achterham"}) == ""


def test_achterham_lidl_off_product_becomes_complete_catalog_link_with_official_gpc():
    db = _mock_db()
    ham = {
        "gtin": GTIN, "product_name": "Achterham",
        "brand": "Zwagerman (Lidl)", "explicit_gpc_brick_code": "",
    }
    with (
        patch.object(linker, "verify_manual_off_proof", return_value=ham),
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "lidl", "receipt_text": "Achterham",
        }),
        patch.object(linker, "assert_external_product_identity_compatible"),
        patch.object(linker, "link_off_product_with_product_type", return_value={
            "ok": True, "linked": True, "global_product": {"id": "zwagerman-achterham"},
        }) as write,
    ):
        begin.return_value.__enter__.return_value = db
        result = linker.confirm_selected_off_catalog_product({
            "receipt_item_id": RECEIPT, "gtin": GTIN, "selection_proof": "signed",
        })
    assert result["linked"] and result["global_product_id"] == "zwagerman-achterham"
    assert write.call_args.kwargs["product_type_assignment"]["product_type_id"] == "gpc:10005781"


def test_automatic_lidl_search_uses_retailer_context_without_fake_product_score():
    item = {
        "receipt_item_id": RECEIPT,
        "retailer_code": "lidl",
        "receipt_line_text": "Achterham",
        "quantity_label": "",
    }
    variants = search._automatic_query_variants(item)
    assert variants[0]["kind"] == "retailer_phrase"
    assert variants[0]["query"] == "achterham lidl"
    assert variants[0]["score_query"] == "achterham"

    queries = []
    def fake_off(query, limit):
        queries.append(query)
        if query == "achterham lidl":
            return ([{
                "code": GTIN, "product_name": "Achterham",
                "brands": "Zwagerman (Lidl)", "quantity": "100 g",
            }], "test-provider")
        return ([], "test-provider")

    with patch.object(search, "_query_off", side_effect=fake_off):
        result = search.search_off_candidates_for_item({
            "mode": "automatic", "limit": 20,
        }, item)
    assert "achterham lidl" in queries
    assert any(row["product_name"] == "Achterham" for row in result["results"])
    assert result["results"][0]["score_breakdown"]["required_product_match"] == 1.0


def test_saved_catalog_link_must_match_target_product_before_claiming_success():
    db = _mock_db()
    db.execute.return_value.mappings.return_value.first.return_value = {"id": "existing-product"}
    with (
        patch.object(linker, "verify_manual_off_proof", return_value=product()),
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "lidl", "receipt_text": "Halfvolle melk"
        }),
        patch.object(linker, "assert_external_product_identity_compatible"),
        patch.object(linker, "_complete_global_product_link_data", return_value={
            "complete": True, "primary_gtin": GTIN,
        }),
        patch.object(linker, "confirm_external_article_for_receipt_item", return_value={
            "status": "confirmed", "global_product_id": "wrong-product",
        }),
    ):
        begin.return_value.__enter__.return_value = db
        with pytest.raises(RuntimeError, match="niet worden bevestigd"):
            linker.confirm_selected_off_catalog_product({
                "receipt_item_id": RECEIPT, "gtin": GTIN, "selection_proof": "valid",
            })


def test_unlinked_overview_uses_the_same_stable_retailer_and_receipt_identity():
    # Same stable store-chain and receipt-label identity must be used by
    # overview, confirmation writer and OFF lookup. Corrected labels win;
    # otherwise prefer normalized labels, then unprocessed OCR raw text.
    import inspect
    from app.services import external_unlinked_articles_service as overview
    from app.services import external_article_confirmation_service as writer
    from app.services import off_search_service as off
    overview_code = inspect.getsource(overview._source_articles)
    writer_code = inspect.getsource(writer._receipt_table_identity)
    off_code = inspect.getsource(off._resolve_receipt_table_line)
    assert "COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '')" in overview_code
    expected = "NULLIF(rtl.corrected_raw_label, ''), NULLIF(rtl.normalized_label, ''), NULLIF(rtl.raw_label, '')"
    for route_code in (overview_code, writer_code, off_code):
        assert expected.replace(", ", ",") in route_code.replace(", ", ",").replace("\\n", "").replace("    ", "")
    assert "store_chain" in writer_code
    assert "store_chain" in overview_code
