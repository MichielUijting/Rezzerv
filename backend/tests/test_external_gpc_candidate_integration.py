from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_SERVICE = ROOT / "backend/app/services/gpc_local_catalog_service.py"
REFERENCE_SERVICE = ROOT / "backend/app/services/gpc_reference_catalog_service.py"
ROUTES = ROOT / "backend/app/api/product_inventory_group_routes.py"
FRONTEND = ROOT / "frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx"


def test_external_classifier_exposes_top_five_candidate_contract():
    service = LOCAL_SERVICE.read_text(encoding="utf-8")
    reference = REFERENCE_SERVICE.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert "rank_external_gpc_candidates" in service
    assert "rank_gpc_candidates" in service
    assert "list_official_gpc_bricks" in service
    assert '"suggestions": suggestions' in service
    assert "suggestions[:5]" in service
    assert "list_official_gpc_bricks" in reference
    assert "gpc_translations" in reference
    assert "brick_description_nl" in reference
    assert "class_description_nl" in reference
    assert "family_description_en" in reference
    assert '"matching_policy": "dutch_gpc_primary_semantic_english_fallback"' in service
    assert "search_text=_payload_text(payload, 'search_text', 'receipt_line_text')" in routes
    assert "product_intent=_payload_text(payload, 'product_intent', 'candidate_product_intent')" in routes


def test_external_ui_contract_requires_automatic_candidates_before_manual_search():
    frontend = FRONTEND.read_text(encoding="utf-8")
    assert "gpcSuggestedBricks" in frontend
    assert "external-auto-gpc-candidates" in frontend
    assert "Waarschijnlijke GS1 GPC Bricks" in frontend
    assert "selectSuggestedGpcBrick" in frontend
    assert "search_text:" in frontend
    assert "product_intent: productIntent" in frontend
    assert "raw.variant" in frontend
