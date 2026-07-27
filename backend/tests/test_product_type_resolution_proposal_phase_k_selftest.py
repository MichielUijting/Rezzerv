from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "app" / "services" / "product_type_resolution_proposal_service.py"
source = SERVICE.read_text(encoding="utf-8")

required_fragments = [
    "build_product_type_operational_actions",
    "classify_gpc_product",
    '"proposal_only": True',
    '"global_product_created": False',
    '"product_type_link_created": False',
    '"read_only": True',
    '"mutates_inventory": False',
    '"requires_user_confirmation": True',
    '"deduplicated_by_household_article": True',
]

for fragment in required_fragments:
    assert fragment in source, f"Ontbrekend voorstelcontract: {fragment}"

assert "INSERT INTO" not in source
assert "UPDATE " not in source
assert "DELETE FROM" not in source

print("PASS product_type_resolution_proposal_sources")
print("PASS product_type_resolution_proposal_read_only")
print("PASS product_type_resolution_proposal_confirmation")
print("PRODUCT_TYPE_RESOLUTION_PROPOSAL_PHASE_K_GREEN")
