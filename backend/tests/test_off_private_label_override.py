"""Huismerkwaarschuwing mag uitsluitend met expliciet, ondertekend OFF-bewijs worden overruled."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import off_manual_catalog_link_service as linker
from app.services.external_product_identity_policy import (
    assert_external_product_identity_compatible,
    external_product_identity_compatibility,
)
from app.services.off_manual_search_proof import issue_manual_off_proof
from app.services import external_article_ui_projection as projection

RECEIPT = "receipt-table-line:ah-crackers"
GTIN = "8718452504435"
PRODUCT = {"gtin": GTIN, "product_name": "Mini crackers nature", "brand": "Lu",
           "quantity": "250 g", "explicit_gpc_brick_code": ""}


def _payload(override=False):
    return {"receipt_item_id": RECEIPT, "gtin": GTIN,
            "selection_proof": issue_manual_off_proof(RECEIPT, PRODUCT),
            **({"override_private_label_conflict": override} if override is not None else {})}


def _linker_context():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.first.return_value = None
    return db


def test_ah_crackers_lu_mismatch_is_a_warning_with_explicit_opt_in_only():
    arguments = {"retailer_code": "ah", "receipt_text": "AH CRACKERS",
                 "candidate_brand": "Lu", "candidate_name": "Mini crackers nature"}
    mismatch = external_product_identity_compatibility(**arguments)
    assert mismatch["reason"] == "private_label_brand_conflict"
    with pytest.raises(ValueError, match="huismerk"):
        assert_external_product_identity_compatible(**arguments)
    accepted = assert_external_product_identity_compatible(
        **arguments, allow_private_label_override=True)
    assert accepted["reason"] == "private_label_brand_conflict"
    assert not accepted["ok"]  # warning remains visible; never claim a genuine brand match


def test_without_opt_in_no_off_link_is_written():
    db = _linker_context()
    with (
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "ah", "receipt_text": "AH CRACKERS", "external_article_code": "1234"}),
        patch.object(linker, "stage_off_product_until_official_gpc") as stage,
        patch.object(linker, "link_off_product_with_product_type") as complete,
    ):
        begin.return_value.__enter__.return_value = db
        with pytest.raises(ValueError, match="huismerk"):
            linker.confirm_selected_off_catalog_product(_payload())
        stage.assert_not_called()
        complete.assert_not_called()


def test_explicit_override_stages_signed_off_product_and_preserves_audit_intent():
    db = _linker_context()
    with (
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "ah", "receipt_text": "AH CRACKERS", "external_article_code": "1234"}),
        patch.object(linker, "_verified_official_gpc_for_exact_name", return_value=""),
        patch.object(linker, "stage_off_product_until_official_gpc",
                     return_value={"ok": True, "cataloged": True,
                                   "classification_pending": True, "global_product_id": "p1"}) as stage,
        patch.object(linker, "link_off_product_with_product_type") as full,
    ):
        begin.return_value.__enter__.return_value = db
        result = linker.confirm_selected_off_catalog_product(_payload(True))
        stage.assert_called_once()
        assert stage.call_args.kwargs["allow_private_label_override"] is True
        assert stage.call_args.kwargs["receipt_item_id"] == RECEIPT
        assert result["cataloged"] is True
        full.assert_not_called()  # no invented GS1 classification or inventory


def test_override_without_actual_ah_house_brand_conflict_is_rejected():
    db = _linker_context()
    with (
        patch.object(linker.engine, "begin") as begin,
        patch.object(linker, "resolve_external_article_identity", return_value={
            "retailer_code": "ah", "receipt_text": "CRACKERS", "external_article_code": "1234"}),
        patch.object(linker, "stage_off_product_until_official_gpc") as stage,
    ):
        begin.return_value.__enter__.return_value = db
        with pytest.raises(ValueError, match="geen huismerkconflict"):
            linker.confirm_selected_off_catalog_product(_payload(True))
        stage.assert_not_called()


@pytest.mark.parametrize("payload_override", ["true", 1, [], {"yes": True}])
def test_override_requires_a_real_json_boolean(payload_override):
    payload = _payload()
    payload["override_private_label_conflict"] = payload_override
    with patch.object(linker.engine, "begin") as begin:
        with pytest.raises(ValueError, match="Ongeldige override"):
            linker.confirm_selected_off_catalog_product(payload)
        begin.assert_not_called()


def test_bad_or_foreign_signed_off_proof_stays_blocked_even_with_opt_in():
    with patch.object(linker.engine, "begin") as begin:
        for proof in ("not-a-proof", issue_manual_off_proof("receipt-table-line:foreign", PRODUCT)):
            payload = _payload(True)
            payload["selection_proof"] = proof
            with pytest.raises(ValueError):
                linker.confirm_selected_off_catalog_product(payload)
        begin.assert_not_called()


def test_read_projection_preserves_explicitly_confirmed_brand_override_not_regular_mismatch():
    row = {"retailer_code": "ah", "receipt_line_text": "AH CRACKERS",
           "external_article_code": "1234"}
    details = {"global_product_id": "p1", "global_product_name": "Mini crackers nature",
               "global_product_brand": "Lu", "primary_gtin": GTIN}
    with (
        patch.object(projection, "get_confirmed_external_article_product_link") as confirmed,
        patch.object(projection, "_central_product_details", return_value=details),
        patch.object(projection, "_catalog_product_by_gtin", return_value=None),
    ):
        confirmed.return_value = {"global_product_id": "p1",
                                  "confirmed_by": "external_databases_off_manual_brand_override"}
        assert projection.project_central_link_truth(MagicMock(), row)["central_link_active"] is True
        confirmed.return_value = {"global_product_id": "p1",
                                  "confirmed_by": "external_databases_off_manual_link"}
        assert projection.project_central_link_truth(MagicMock(), row)["central_link_active"] is False
