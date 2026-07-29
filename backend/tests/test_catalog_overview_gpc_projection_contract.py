from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PAGE = ROOT / "frontend/src/features/catalog/CatalogPage.jsx"


def test_confirmed_gpc_assignment_is_projected_into_catalog_overview():
    source = CATALOG_PAGE.read_text(encoding="utf-8")

    assert "enrichCatalogItemWithGpc" in source
    assert "/gpc-brick" in source
    assert "assignment.brick_description" in source
    assert "assignment.brick_description_en" in source
    assert "product_type: confirmedDescription" in source
    assert "gpc_brick_code: assignment.brick_code" in source
    assert "quality_status: 'Compleet'" in source
    assert "Promise.all(catalogItems.map(enrichCatalogItemWithGpc))" in source


def test_projected_product_type_drives_filter_sort_and_export():
    source = CATALOG_PAGE.read_text(encoding="utf-8")

    assert "updateSort('product_type')" in source
    assert "String(item.product_type || '').toLowerCase().includes" in source
    assert "item.product_type, item.source" in source
    assert "updateSort('quality_status')" in source
