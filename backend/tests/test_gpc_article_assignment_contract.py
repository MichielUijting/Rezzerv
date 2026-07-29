from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend/app/services/gpc_article_assignment_service.py"
GUARD = ROOT / "backend/app/services/article_detail_write_guard.py"
FRAME = ROOT / "frontend/src/features/catalog/CatalogGpcFrame.jsx"
DETAIL = ROOT / "frontend/src/features/catalog/CatalogDetailPageV2.jsx"
ROUTER = ROOT / "frontend/src/app/router/AppRouter.jsx"
CSS = ROOT / "frontend/src/features/catalog/catalog.css"


def test_backend_routes_cover_search_read_write_and_clear_for_catalog():
    source = SERVICE.read_text(encoding="utf-8")
    assert '@app.get("/api/gpc/bricks")' in source
    assert '@app.get("/api/catalog/{global_product_id}/gpc-brick")' in source
    assert '@app.put("/api/catalog/{global_product_id}/gpc-brick")' in source
    assert '@app.delete("/api/catalog/{global_product_id}/gpc-brick")' in source
    assert "global_product_gpc_bricks" in source
    assert "household_article_gpc_bricks" not in source


def test_assignment_targets_existing_global_product_and_known_brick():
    source = SERVICE.read_text(encoding="utf-8")
    assert "FROM global_products" in source
    assert "global_product_id = :global_product_id" in source
    assert "require_inventory_write_context" in source
    assert "SELECT 1 FROM gpc_bricks WHERE brick_code" in source


def test_dutch_text_has_official_english_fallback():
    source = SERVICE.read_text(encoding="utf-8")
    assert "COALESCE((SELECT translated_text FROM gpc_translations" in source
    assert "brick_description_en" in source
    assert "tr.language_code='nl'" in source


def test_routes_are_registered_unconditionally_before_guard_inventory():
    source = GUARD.read_text(encoding="utf-8")
    install = source.index("install_gpc_article_assignment_routes(main_module)")
    discover = source.index("protected_routes = discover_article_detail_write_routes(app)")
    assert install < discover
    assert 'hasattr(main_module, "require_household_context")' not in source
    assert '"set_catalog_product_gpc_brick"' in source
    assert '"clear_catalog_product_gpc_brick"' in source


def test_frontend_integrates_frame_natively_in_catalog_detail():
    frame = FRAME.read_text(encoding="utf-8")
    detail = DETAIL.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert "createPortal" not in frame
    assert "document.querySelector" not in frame
    assert "functionalError" in frame
    assert "GPC classificeren" in frame
    assert "GPC wijzigen" in frame
    assert "editorOpen" in frame
    assert "CatalogGpcFrame globalProductId={globalProductId}" in detail
    assert "CatalogDetailPageV2" in router
    assert "CatalogDetailWithGpc" not in router
    assert "'/voorraad/:articleId/gpc'" not in router
    assert "ArticleGpcInlineSummary" not in router
    assert ".rz-catalog-gpc-section" in css
    assert ".rz-catalog-gpc-result" in css
