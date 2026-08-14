from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UITPAKKEN = ROOT / "frontend/src/features/stores/StoreBatchDetailPage.jsx"
MAIN = ROOT / "backend/app/main.py"


def test_uitpakken_uses_canonical_household_admin_authority_for_location_management():
    text = UITPAKKEN.read_text(encoding="utf-8")
    assert "isHouseholdAdminFromContext" in text
    assert "const canManageLocations = isHouseholdAdminFromContext()" in text
    assert "const canManageLocations = isHouseholdAdminFromContext(household)" not in text
    assert "const canManageLocations = !isViewer" not in text


def test_uitpakken_admin_can_create_space_and_sublocation_inline_and_apply_result():
    text = UITPAKKEN.read_text(encoding="utf-8")
    assert "data-testid=\"receipt-location-create-space\"" in text
    assert "data-testid=\"receipt-location-create-sublocation\"" in text
    assert "await fetchJson('/api/spaces'" in text
    assert "await fetchJson('/api/sublocations'" in text
    assert "const nextOptions = await refreshLocationOptions()" in text
    assert "await applyPickedLocation(String(created.id), nextOptions)" in text


def test_location_create_routes_remain_server_side_admin_only():
    text = MAIN.read_text(encoding="utf-8")

    space_start = text.index('@app.post("/api/spaces")')
    space_end = text.index('@app.put("/api/spaces/{space_id}")', space_start)
    space_block = text[space_start:space_end]
    assert "require_household_admin_context" in space_block

    sub_start = text.index('@app.post("/api/sublocations")')
    sub_end = text.index('@app.put("/api/sublocations/{sublocation_id}")', sub_start)
    sub_block = text[sub_start:sub_end]
    assert "require_household_admin_context" in sub_block
    assert 'str(space["household_id"])' in sub_block


def test_uitpakken_receipt_table_opens_picker_and_preserves_b3_location_handling():
    text = UITPAKKEN.read_text(encoding="utf-8")
    assert "openLocationPicker(line.id, 'handling')" in text
    assert "locationPickerSaveMode === 'handling'" in text
    assert "await handleLocationChoice(pickerEntry, nextLocationId, locationOptionsOverride || locationOptions)" in text
    assert "availableLocationOptions = locationOptions" in text
    assert "directLocationOption(availableLocationOptions)" in text
    assert "availableLocationOptions.find(" in text
    assert "await handleLocationChoice(pickerEntry, '__standard__')" in text
    assert "nextOverride: STOCK" in text
    assert "nextLocationId: ''" in text
    assert "applyPickedLocation(String(created.id), nextOptions)" in text
    assert "availableLocationOptions = locationOptions" in text
