from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app").exists():
    ROOT = ROOT / "backend"

SERVICE = ROOT / "app" / "services" / "product_type_manual_catalog_search_service.py"
ROUTES = ROOT / "app" / "api" / "product_inventory_group_routes.py"

service_source = SERVICE.read_text(encoding="utf-8")
route_source = ROUTES.read_text(encoding="utf-8")

for fragment in [
    "search_product_type_catalog",
    '"basis": "manual_gpc_catalog_search"',
    '"read_only": True',
    '"mutates_inventory": False',
    '"creates_global_products": False',
    '"creates_product_type_links": False',
    '"selection_requires_confirmation": True',
    "gpc_product_groups",
]:
    assert fragment in service_source, f"Ontbrekend handmatig zoekcontract: {fragment}"

assert "INSERT INTO" not in service_source
assert "UPDATE " not in service_source
assert "DELETE FROM" not in service_source

for fragment in [
    "'/api/households/{household_id}/product-type-catalog-search'",
    "search_product_type_catalog(",
    "household_article_id: str = Query(...)",
    "q: str = Query(...)",
]:
    assert fragment in route_source, f"Ontbrekend API-contract: {fragment}"

print("PASS product_type_manual_catalog_search_sources")
print("PASS product_type_manual_catalog_search_read_only")
print("PASS product_type_manual_catalog_search_confirmation_gate")
print("PRODUCT_TYPE_MANUAL_CATALOG_SEARCH_PHASE_L_GREEN")
