"""A stored OFF GTIN is not an operational match while GS1 is pending."""

from unittest.mock import MagicMock

from app.services import external_article_ui_projection as projection


def test_catalog_gtin_fallback_cannot_promote_pending_gpc(monkeypatch):
    monkeypatch.setattr(projection, "get_confirmed_external_article_product_link", lambda *args, **kwargs: None)
    monkeypatch.setattr(projection, "_catalog_product_by_gtin", lambda *args: {
        "global_product_id": "pending-achterham",
        "global_product_name": "Achterham",
        "global_product_brand": "Zwagerman",
        "primary_gtin": "8718452504435",
    })
    monkeypatch.setattr(projection, "_complete_global_product_link_data", lambda *args: {"complete": False})
    result = projection.project_central_link_truth(MagicMock(), {
        "retailer_code": "lidl",
        "receipt_line_text": "Achterham BL",
        "external_article_code": "6604471",
        "candidates": [{"gtin": "8718452504435", "candidate_name": "Achterham"}],
    })
    assert result["central_link_active"] is False
    assert result["is_linked_to_catalog"] is False


def test_catalog_gtin_fallback_requires_official_gpc_and_valid_identity(monkeypatch):
    monkeypatch.setattr(projection, "get_confirmed_external_article_product_link", lambda *args, **kwargs: None)
    monkeypatch.setattr(projection, "_catalog_product_by_gtin", lambda *args: {
        "global_product_id": "classified-achterham",
        "global_product_name": "Achterham",
        "global_product_brand": "Zwagerman",
        "primary_gtin": "8718452504435",
    })
    monkeypatch.setattr(projection, "_complete_global_product_link_data", lambda *args: {"complete": True})
    monkeypatch.setattr(projection, "_central_product_details", lambda *args: {
        "global_product_name": "Achterham", "global_product_brand": "Zwagerman",
        "primary_gtin": "8718452504435", "product_type_id": "gpc:10005781",
    })
    result = projection.project_central_link_truth(MagicMock(), {
        "retailer_code": "lidl", "receipt_line_text": "Achterham BL",
        "candidates": [{"gtin": "8718452504435"}],
    })
    assert result["central_link_active"] is True
    assert result["linked_gtin"] == "8718452504435"
