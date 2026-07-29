from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PAGE = ROOT / "frontend/src/features/catalog/CatalogPage.jsx"
CATALOG_ROUTES = ROOT / "backend/app/api/catalog_routes.py"
CATALOG_DETAIL = ROOT / "frontend/src/features/catalog/CatalogDetailPageV2.jsx"
CATALOG_CSS = ROOT / "frontend/src/features/catalog/catalog.css"


def test_confirmed_gpc_assignment_is_projected_by_catalog_backend_query():
    source = CATALOG_ROUTES.read_text(encoding="utf-8")

    assert "global_product_gpc_bricks catalog_gpc" in source
    assert "gpc_bricks catalog_brick" in source
    assert "tr.entity_type = 'brick'" in source
    assert "AS product_type" in source
    assert "AS gpc_brick_code" in source


def test_catalog_overview_uses_backend_pagination_without_n_plus_one_requests():
    frontend = CATALOG_PAGE.read_text(encoding="utf-8")
    backend = CATALOG_ROUTES.read_text(encoding="utf-8")

    assert "/api/catalog?${params.toString()}" in frontend
    assert "limit: String(PAGE_SIZE)" in frontend
    assert "offset: String((page - 1) * PAGE_SIZE)" in frontend
    assert "sort_by: sort.key" in frontend
    assert "sort_direction: sort.direction" in frontend
    assert "Promise.all(catalogItems.map(enrichCatalogItemWithGpc))" not in frontend
    assert "enrichCatalogItemWithGpc" not in frontend
    assert "/api/catalog?limit=2000" not in frontend
    assert "Query(default=10, ge=1, le=2000)" in backend
    assert "offset: int = Query(default=0, ge=0)" in backend
    assert "LIMIT :limit OFFSET :offset" in backend
    assert "SELECT COUNT(*)" in backend


def test_backend_pagination_drives_filter_sort_total_and_exported_product_type():
    frontend = CATALOG_PAGE.read_text(encoding="utf-8")
    backend = CATALOG_ROUTES.read_text(encoding="utf-8")

    assert "primaryGtin: 'primary_gtin'" in frontend
    assert "productType: 'product_type'" in frontend
    assert "householdArticleCount: 'household_article_count'" in frontend
    assert "setTotal(Number(data?.total || 0))" in frontend
    assert "Math.ceil(total / PAGE_SIZE)" in frontend
    assert "item.product_type, item.source" in frontend
    assert "order_expression = expressions.get(sort_by" in backend
    assert "LOWER({expressions[key]}) LIKE" in backend
    assert '"total": total' in backend


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
