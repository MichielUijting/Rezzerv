from pathlib import Path

ROOT = Path.cwd()
SERVICE = ROOT / "app" / "services" / "product_type_manual_selection_preview_service.py"
source = SERVICE.read_text(encoding="utf-8")

required_fragments = [
    "manual_gpc_selection_confirmation_preview",
    "manual_gpc_catalog_search",
    '"read_only": True',
    '"mutates_inventory": False',
    '"creates_global_products": False',
    '"creates_product_type_links": False',
    '"selection_validated": True',
    '"confirmation_required": True',
    '"confirmation_status": "pending"',
    "build_product_type_resolution_proposals",
]

for fragment in required_fragments:
    assert fragment in source, f"Ontbrekend selectiepreviewcontract: {fragment}"

assert "INSERT INTO" not in source
assert "UPDATE " not in source
assert "DELETE FROM" not in source

print("PASS product_type_manual_selection_preview_sources")
print("PASS product_type_manual_selection_preview_read_only")
print("PASS product_type_manual_selection_preview_confirmation_gate")
print("PRODUCT_TYPE_MANUAL_SELECTION_PREVIEW_PHASE_M_GREEN")
