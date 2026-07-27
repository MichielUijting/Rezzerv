from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app").exists():
    ROOT = ROOT / "backend"

SERVICE = ROOT / "app" / "services" / "product_type_manual_selection_confirmation_service.py"
source = SERVICE.read_text(encoding="utf-8")

required_fragments = [
    "confirm_product_type_manual_selection",
    "explicit confirmation is required",
    "build_product_type_manual_selection_preview",
    "get_or_create_global_product",
    "link_global_product_to_inventory_group_with_connection",
    '"confirmed_by_user": True',
    '"confirmation_status": "confirmed"',
    '"mutates_inventory": False',
    '"creates_inventory_event": False',
    '"mutates_purchase_list": False',
]

for fragment in required_fragments:
    assert fragment in source, f"Ontbrekend bevestigingscontract: {fragment}"

assert "UPDATE inventory " not in source
assert "INSERT INTO inventory " not in source
assert "DELETE FROM inventory " not in source

print("PASS product_type_manual_selection_confirmation_sources")
print("PASS product_type_manual_selection_confirmation_explicit_gate")
print("PASS product_type_manual_selection_confirmation_no_inventory_mutation")
print("PRODUCT_TYPE_MANUAL_SELECTION_CONFIRMATION_PHASE_N_GREEN")
