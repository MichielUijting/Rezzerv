from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_SERVICE = ROOT / "backend/app/services/gpc_local_catalog_service.py"
REFERENCE_SERVICE = ROOT / "backend/app/services/gpc_reference_catalog_service.py"
ROUTES = ROOT / "backend/app/api/product_inventory_group_routes.py"
ED2_CANDIDATES = ROOT / "frontend/src/features/externalDatabases/OffCandidatePanel.jsx"
ED2_GPC = ROOT / "frontend/src/features/externalDatabases/Ed2GpcClassificationPanel.jsx"


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
    assert "gpc_product_groups" in reference
    assert "ensure_bundled_dutch_gpc_reference" in reference
    assert "'gs1_gpc_nl' AS reference_source" in reference
    assert "gpc_bricks_2026_05_en.json" not in reference
    assert '"matching_policy": "dutch_gpc_only"' in service
    assert "search_text=_payload_text(payload, 'search_text', 'receipt_line_text')" in routes
    assert "product_intent=_payload_text(payload, 'product_intent', 'candidate_product_intent')" in routes
    assert "category_tags=payload.get('category_tags')" in routes


def test_ed2_candidate_preview_and_official_gpc_proposals_remain_available():
    candidates = ED2_CANDIDATES.read_text(encoding="utf-8")
    gpc = ED2_GPC.read_text(encoding="utf-8")
    # No v1-only automatic GPC controls, but ED2 must still offer automatic
    # OFF candidates, manual OFF search and official Dutch GS1 suggestions.
    assert "/api/external-databases/products/search-preview" in candidates
    assert "mode: 'automatic'" in candidates
    assert "Zelf zoeken in OFF" in candidates
    assert "/gpc-brick" in gpc
    assert "Waarschijnlijke GS1-classificaties" in gpc
    assert "candidates.slice(0, 5)" in gpc
    assert "ed2-gpc-candidates" in gpc
    assert "/api/catalog/gpc/bricks?query=" in gpc
    assert "/api/external-databases/off/classify-pending" in gpc
