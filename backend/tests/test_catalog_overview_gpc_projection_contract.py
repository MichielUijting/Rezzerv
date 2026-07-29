from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PAGE = ROOT / "frontend/src/features/catalog/CatalogPage.jsx"
CATALOG_ROUTES = ROOT / "backend/app/api/catalog_routes.py"
CATALOG_DETAIL = ROOT / "frontend/src/features/catalog/CatalogDetailPageV2.jsx"
CATALOG_CSS = ROOT / "frontend/src/features/catalog/catalog.css"


def test_confirmed_gpc_assignment_is_projected_into_catalog_overview():
    source = CATALOG_PAGE.read_text(encoding="utf-8")

    assert "enrichCatalogItemWithGpc" in source
    assert "/gpc-brick" in source
    assert "assignment.brick_description" in source
    assert "assignment.brick_description_en" in source
    assert "product_type: confirmedDescription" in source
    assert "gpc_brick_code: assignment.brick_code" in source
    assert "Promise.all(catalogItems.map(enrichCatalogItemWithGpc))" in source


def test_projected_product_type_drives_filter_sort_and_export():
    source = CATALOG_PAGE.read_text(encoding="utf-8")

    assert "updateSort('product_type')" in source
    assert "String(item.product_type || '').toLowerCase().includes" in source
    assert "item.product_type, item.source" in source


def test_catalog_status_is_removed_from_backend_frontend_export_and_detail():
    page = CATALOG_PAGE.read_text(encoding="utf-8")
    routes = CATALOG_ROUTES.read_text(encoding="utf-8")
    detail = CATALOG_DETAIL.read_text(encoding="utf-8")
    css = CATALOG_CSS.read_text(encoding="utf-8")

    assert "quality_status" not in page
    assert "qualityStatus" not in page
    assert ">Status <" not in page
    assert "'Status'" not in page
    assert "_quality_status" not in routes
    assert "quality_status:" not in routes
    assert "Kwaliteitsstatus" not in detail
    assert "rz-catalog-status" not in css
    assert "rz-catalog-col-status" not in css
