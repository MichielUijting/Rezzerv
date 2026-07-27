from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app").exists():
    ROOT = ROOT / "backend"

ROUTES = ROOT / "app" / "api" / "product_inventory_group_routes.py"
source = ROUTES.read_text(encoding="utf-8")

required_fragments = [
    "confirm_product_type_manual_selection",
    "@router.post('/api/households/{household_id}/product-type-selection/confirm')",
    "household_article_id=str(payload.get('household_article_id') or '').strip()",
    "gpc_brick_code=str(payload.get('gpc_brick_code') or '').strip()",
    "confirmed=bool(payload.get('confirmed', False))",
    "raise HTTPException(status_code=400, detail=str(exc))",
]

for fragment in required_fragments:
    assert fragment in source, f"Ontbrekend API-contract: {fragment}"

assert "@router.get('/api/households/{household_id}/product-type-selection/confirm')" not in source

print("PASS product_type_manual_selection_confirmation_api_source")
print("PASS product_type_manual_selection_confirmation_api_explicit_gate")
print("PRODUCT_TYPE_MANUAL_SELECTION_CONFIRMATION_API_GREEN")
