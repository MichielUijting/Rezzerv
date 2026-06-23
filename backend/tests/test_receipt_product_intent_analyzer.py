from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line


def test_analyzes_grated_cheese_receipt_line():
    analysis = analyze_receipt_product_line("ITALIAANSE RASP KAAS 200G", retailer_code="lidl")

    assert analysis.normalized_text == "italiaanse rasp kaas 200g"
    assert analysis.product_intent == "zuivel.kaas"
    assert analysis.category == "zuivel"
    assert analysis.product_type == "kaas"
    assert "italiaans" in analysis.variant_terms
    assert "rasp" in analysis.variant_terms
    assert analysis.quantity_amount == "200"
    assert analysis.quantity_unit == "g"
    assert analysis.quantity_label == "200 g"
    assert "kaas" in analysis.searchable_terms
    assert analysis.requires_user_confirmation is False


def test_analyzes_halfvolle_melk_with_quantity():
    analysis = analyze_receipt_product_line("HALFVOLLE MELK 1L", retailer_code="lidl")

    assert analysis.product_intent == "zuivel.melk"
    assert analysis.category == "zuivel"
    assert analysis.product_type == "melk"
    assert "halfvolle" in analysis.variant_terms
    assert analysis.quantity_amount == "1"
    assert analysis.quantity_unit == "l"
    assert analysis.quantity_label == "1 l"


def test_analyzes_lidl_specific_abbreviated_kruidenmix():
    analysis = analyze_receipt_product_line("Mexicaanse kruidenm.", retailer_code="lidl")

    assert analysis.product_intent == "kruiden.specerijenmix"
    assert analysis.category == "kruiden"
    assert analysis.product_type == "specerijenmix"
    assert "mexicaanse kruidenm" in analysis.searchable_terms


def test_unknown_receipt_line_requires_confirmation():
    analysis = analyze_receipt_product_line("ONLEESBAAR ARTIKEL X9", retailer_code="lidl")

    assert analysis.product_intent == ""
    assert analysis.category == ""
    assert analysis.product_type == ""
    assert analysis.requires_user_confirmation is True
    assert "onleesbaar artikel x9" in analysis.searchable_terms
