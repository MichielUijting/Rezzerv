"""Regression: a same-label AH receipt with another code is a distinct article."""
from unittest.mock import MagicMock, patch

from app.services import external_article_product_link_service as links


def _conn():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None
    return conn


def _valid_product():
    return {
        "has_valid_primary_gtin": True,
        "has_matching_gtin_identity": True,
        "is_generic_catalog_product": False,
        "has_active_official_gpc": False,
    }


def test_staging_845556_uses_number_not_same_name_for_conflicts():
    conn = _conn()
    # First query for global product; next for conflicting link;
    # pending lookup; then update, insert and reread.
    conn.execute.return_value.mappings.return_value.first.side_effect = [
        {"id": "product-1", "status": "active"},
        None,
        None,
        {"id": "stage-1", "status": "classification_pending",
         "global_product_id": "product-1", "retailer_code": "ah"},
    ]
    with patch.object(links, "_complete_global_product_link_data", return_value=_valid_product()), \
         patch.object(links, "_serialize_external_article_product_link",
                      return_value={"status": "classification_pending"}):
        result = links.stage_external_article_product_link_without_gpc(
            conn, retailer_code="ah", receipt_text="AH BOUILLON",
            external_article_code="845556", global_product_id="product-1",
        )
    assert result["status"] == "classification_pending"
    statements = [str(call.args[0]) for call in conn.execute.call_args_list]
    for statement in statements:
        if "external_article_product_links" in statement and any(
            keyword in statement for keyword in ("SELECT id", "SELECT link.*", "UPDATE")
        ):
            assert "external_article_code = :external_article_code" in statement
            assert "receipt_text_normalized = :receipt_text_normalized" not in statement


def test_pending_lookup_with_code_does_not_fall_back_to_same_name():
    conn = _conn()
    links.get_pending_classification_external_article_link(
        conn, retailer_code="ah", receipt_text="AH BOUILLON",
        external_article_code="845556",
    )
    assert conn.execute.call_count == 1
    statement = str(conn.execute.call_args.args[0])
    assert "link.external_article_code = :identity_value" in statement
    assert "link.receipt_text_normalized = :identity_value" not in statement


def test_pending_lookup_without_code_checks_only_unnumbered_links():
    conn = _conn()
    links.get_pending_classification_external_article_link(
        conn, retailer_code="ah", receipt_text="AH BOUILLON",
    )
    statement = str(conn.execute.call_args.args[0])
    assert "COALESCE(TRIM(link.external_article_code), '') = ''" in statement
