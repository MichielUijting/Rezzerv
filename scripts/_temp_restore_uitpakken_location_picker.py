from pathlib import Path

product = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
text = product.read_text(encoding='utf-8')

old_create = "      await applyPickedLocation(String(created.id))"
new_create = "      await applyPickedLocation(String(created.id), nextOptions)"
if text.count(old_create) != 1:
    raise SystemExit(f'STOP: create apply anchor count={text.count(old_create)}')
text = text.replace(old_create, new_create, 1)

old_signature = "  async function applyPickedLocation(locationId) {\n    const nextLocationId = String(locationId ?? '')"
new_signature = "  async function applyPickedLocation(locationId, locationOptionsOverride = null) {\n    const nextLocationId = String(locationId ?? '')"
if text.count(old_signature) != 1:
    raise SystemExit(f'STOP: apply signature anchor count={text.count(old_signature)}')
text = text.replace(old_signature, new_signature, 1)

old_handling = "    if (locationPickerSaveMode === 'handling') {\n      await handleLocationChoice(pickerEntry, nextLocationId)\n      closeLocationPicker()"
new_handling = "    if (locationPickerSaveMode === 'handling') {\n      await handleLocationChoice(pickerEntry, nextLocationId, locationOptionsOverride || locationOptions)\n      closeLocationPicker()"
if text.count(old_handling) != 1:
    raise SystemExit(f'STOP: handling route anchor count={text.count(old_handling)}')
text = text.replace(old_handling, new_handling, 1)

old_choice = "  async function handleLocationChoice(entry, nextValue) {\n    const householdId"
new_choice = "  async function handleLocationChoice(entry, nextValue, availableLocationOptions = locationOptions) {\n    const householdId"
if text.count(old_choice) != 1:
    raise SystemExit(f'STOP: handle signature anchor count={text.count(old_choice)}')
text = text.replace(old_choice, new_choice, 1)

old_direct = "    const directLocation = directLocationOption(locationOptions)"
new_direct = "    const directLocation = directLocationOption(availableLocationOptions)"
if text.count(old_direct) != 1:
    raise SystemExit(f'STOP: direct options anchor count={text.count(old_direct)}')
text = text.replace(old_direct, new_direct, 1)

old_find = "      const selectedLocation = locationOptions.find(\n        (location) => String(location.id) === String(nextValue),\n      ) || null"
new_find = "      const selectedLocation = availableLocationOptions.find(\n        (location) => String(location.id) === String(nextValue),\n      ) || null"
if text.count(old_find) != 1:
    raise SystemExit(f'STOP: selected options anchor count={text.count(old_find)}')
text = text.replace(old_find, new_find, 1)

product.write_text(text, encoding='utf-8', newline='\n')

contract = Path('backend/tests/test_uitpakken_location_admin_contract.py')
contract_text = contract.read_text(encoding='utf-8')
old_contract = "    assert \"nextLocationId: ''\" in text"
new_contract = "    assert \"nextLocationId: ''\" in text\n    assert \"applyPickedLocation(String(created.id), nextOptions)\" in text\n    assert \"availableLocationOptions = locationOptions\" in text"
if contract_text.count(old_contract) != 1:
    raise SystemExit(f'STOP: contract race anchor count={contract_text.count(old_contract)}')
contract.write_text(contract_text.replace(old_contract, new_contract, 1), encoding='utf-8', newline='\n')

print('PASS: new-location option race fix applied')
