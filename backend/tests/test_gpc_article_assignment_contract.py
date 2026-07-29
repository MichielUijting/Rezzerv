from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GPC_ROUTES = ROOT / "backend/app/api/catalog_gpc_routes.py"
CATALOG_ROUTES = ROOT / "backend/app/api/catalog_routes.py"
GUARD = ROOT / "backend/app/services/article_detail_write_guard.py"
FRAME = ROOT / "frontend/src/features/catalog/CatalogGpcFrame.jsx"
ACTION_PAGE = ROOT / "frontend/src/features/catalog/CatalogGpcActionPage.jsx"
CATALOG_PAGE = ROOT / "frontend/src/features/catalog/CatalogPage.jsx"
DETAIL = ROOT / "frontend/src/features/catalog/CatalogDetailPageV2.jsx"
FRONTEND_ROUTER = ROOT / "frontend/src/app/router/AppRouter.jsx"
CSS = ROOT / "frontend/src/features/catalog/catalog.css"


def test_catalog_router_contains_real_gpc_runtime_routes():
    from app.api.catalog_routes import router

    routes = {
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert ("GET", "/api/catalog/gpc/bricks") in routes
    assert ("GET", "/api/catalog/{global_product_id}/gpc-brick") in routes
    assert ("PUT", "/api/catalog/{global_product_id}/gpc-brick") in routes
    assert ("DELETE", "/api/catalog/{global_product_id}/gpc-brick") in routes


def test_main_catalog_router_mount_produces_expected_public_paths():
    from fastapi import FastAPI
    from app.api.catalog_routes import router

    app = FastAPI()
    app.include_router(router)
    routes = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert ("GET", "/api/catalog/gpc/bricks") in routes
    assert ("GET", "/api/catalog/{global_product_id}/gpc-brick") in routes
    assert ("PUT", "/api/catalog/{global_product_id}/gpc-brick") in routes
    assert ("DELETE", "/api/catalog/{global_product_id}/gpc-brick") in routes


def test_assignment_targets_existing_global_product_and_known_brick():
    source = GPC_ROUTES.read_text(encoding="utf-8")
    assert "FROM global_products" in source
    assert "global_product_id" in source
    assert "SELECT 1 FROM gpc_bricks WHERE brick_code" in source
    assert "global_product_gpc_bricks" in source
    assert "household_article_gpc_bricks" not in source


def test_dutch_text_has_official_english_fallback():
    source = GPC_ROUTES.read_text(encoding="utf-8")
    assert "COALESCE((SELECT translated_text FROM gpc_translations" in source
    assert "brick_description_en" in source
    assert "tr.language_code='nl'" in source


def test_existing_confirmed_product_group_is_migrated_idempotently():
    source = GPC_ROUTES.read_text(encoding="utf-8")
    assert "product_group_memberships" in source
    assert "product_inventory_groups" in source
    assert "confirmed_by_user" in source
    assert "migrated_confirmed_product_group" in source
    assert "ON CONFLICT(global_product_id) DO NOTHING" in source
    assert "_migrate_confirmed_legacy_assignment" in source
    assert "global_product_gpc_migration_suppressions" in source


def test_registration_is_decoupled_from_article_write_guard():
    catalog_source = CATALOG_ROUTES.read_text(encoding="utf-8")
    guard_source = GUARD.read_text(encoding="utf-8")
    assert "router.include_router(catalog_gpc_router)" in catalog_source
    assert "install_gpc_article_assignment_routes" not in guard_source
    assert '"set_catalog_product_gpc_brick"' in guard_source
    assert '"clear_catalog_product_gpc_brick"' in guard_source


def test_catalog_exposes_direct_gpc_action_button_and_normal_route():
    catalog = CATALOG_PAGE.read_text(encoding="utf-8")
    action = ACTION_PAGE.read_text(encoding="utf-8")
    router = FRONTEND_ROUTER.read_text(encoding="utf-8")

    assert "GPC classificeren" in catalog
    assert "navigate('/catalogus/gpc-classificeren')" in catalog
    assert "path: '/catalogus/gpc-classificeren'" in router
    assert "CatalogGpcActionPage" in router
    assert "Zoeken op artikelnaam, merk, barcode, GTIN of EAN" in action
    assert "/api/catalog?limit=2000" in action
    assert "/gpc-brick" in action
    assert "/api/catalog/gpc/bricks" in action
    assert "De bestaande bevestigde GPC-classificatie is gevonden." in action
    assert "De GPC Brick is bevestigd en opgeslagen" in action


def test_frontend_integrates_frame_natively_without_unreliable_suggestion():
    frame = FRAME.read_text(encoding="utf-8")
    detail = DETAIL.read_text(encoding="utf-8")
    router = FRONTEND_ROUTER.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert "createPortal" not in frame
    assert "document.querySelector" not in frame
    assert "functionalError" in frame
    assert "GPC classificeren" in frame
    assert "GPC wijzigen" in frame
    assert "editorOpen" in frame
    assert "/api/catalog/gpc/bricks" in frame
    assert "Voorgestelde classificatie" not in frame
    assert "Voorstel bevestigen" not in frame
    assert "Overgenomen uit eerder bevestigde GPC-productgroep" in frame
    assert "CatalogGpcFrame globalProductId={globalProductId}" in detail
    assert "CatalogDetailPageV2" in router
    assert "CatalogDetailWithGpc" not in router
    assert "'/voorraad/:articleId/gpc'" not in router
    assert "ArticleGpcInlineSummary" not in router
    assert ".rz-catalog-gpc-section" in css
    assert ".rz-catalog-gpc-result" in css
