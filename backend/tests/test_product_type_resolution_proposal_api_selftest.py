from pathlib import Path

ROOT = Path.cwd()
ROUTES = ROOT / "app" / "api" / "product_inventory_group_routes.py"
source = ROUTES.read_text(encoding="utf-8")

required_fragments = [
    "build_product_type_resolution_proposals",
    "@router.get('/api/households/{household_id}/product-type-resolution-proposals')",
    "def product_type_resolution_proposals(household_id: str):",
    "return build_product_type_resolution_proposals(household_id)",
]

for fragment in required_fragments:
    assert fragment in source, f"Ontbrekend Producttypevoorstel-API-contract: {fragment}"

print("PASS product_type_resolution_proposal_api_source")
print("PASS product_type_resolution_proposal_api_contract")
print("PRODUCT_TYPE_RESOLUTION_PROPOSAL_API_GREEN")
