from app.services.product_intent_classifier import classify_product_intent
from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line


def test_lidl_gouda_belegen_gerasp_is_recognized_as_cheese():
    analysis = analyze_receipt_product_line("Gouda belegen gerasp", retailer_code="lidl")

    assert analysis.product_intent == "zuivel.kaas"
    assert analysis.category == "zuivel"
    assert analysis.product_type == "kaas"
    assert "gouda" in analysis.variant_terms
    assert "belegen" in analysis.variant_terms
    assert "gerasp" in analysis.variant_terms or "geraspt" in analysis.variant_terms
    assert "oud" not in analysis.variant_terms


def test_lidl_creme_fraiche_receipt_line_is_recognized():
    assert classify_product_intent("Crème fraiche 30%", retailer_code="lidl") == "zuivel.creme_fraiche"
    assert classify_product_intent("Creme fraiche 30%", retailer_code="lidl") == "zuivel.creme_fraiche"
    assert classify_product_intent("Cr me fraiche 30%", retailer_code="lidl") == "zuivel.creme_fraiche"


def test_lidl_creme_frache_ocr_receipt_line_is_recognized():
    assert classify_product_intent("Crème frache 30%", retailer_code="lidl") == "zuivel.creme_fraiche"
    assert classify_product_intent("Creme frache 30%", retailer_code="lidl") == "zuivel.creme_fraiche"
    assert classify_product_intent("Cr me frache 30%", retailer_code="lidl") == "zuivel.creme_fraiche"


def test_lidl_receipt_terms_for_rice_and_pasta_are_recognized():
    assert classify_product_intent("Duurzame basmati rijst", retailer_code="lidl") == "graan.rijst"
    assert classify_product_intent("Gebronsde pasta linguin", retailer_code="lidl") == "pasta.droog"
