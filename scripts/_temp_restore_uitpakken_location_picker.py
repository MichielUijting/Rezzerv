from pathlib import Path

product = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
text = product.read_text(encoding='utf-8')

replacements = [
    (
        "  const [locationPickerMode, setLocationPickerMode] = useState('single')\n  const [activeLocationSpaceId, setActiveLocationSpaceId] = useState('')",
        "  const [locationPickerMode, setLocationPickerMode] = useState('single')\n  const [locationPickerSaveMode, setLocationPickerSaveMode] = useState('legacy')\n  const [activeLocationSpaceId, setActiveLocationSpaceId] = useState('')",
    ),
    (
        "    setLocationPickerMode('single')\n    setActiveLocationSpaceId('')",
        "    setLocationPickerMode('single')\n    setLocationPickerSaveMode('legacy')\n    setActiveLocationSpaceId('')",
    ),
    (
        "  async function openLocationPicker(lineId) {\n    setLocationPickerMode('single')\n    setLocationPickerLineId(String(lineId))",
        "  async function openLocationPicker(lineId, saveMode = 'legacy') {\n    setLocationPickerMode('single')\n    setLocationPickerSaveMode(saveMode)\n    setLocationPickerLineId(String(lineId))",
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f'STOP: state/open picker anchor count={text.count(old)}')
    text = text.replace(old, new, 1)

old_table = '''                      <td onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
                        <select
                          className="rz-input rz-inline-input"
                          value={entry.draft.locationId || ''}
                          disabled={busyLineId === line.id || isProcessingBatch || isViewer}
                          aria-label={`Locatie voor ${line.article_name_raw}`}
                          data-testid={`receipt-line-location-select-${line.id}`}
                          onChange={(event) => handleLocationChoice(entry, event.target.value)}
                        >
                          <option value="">Kies locatie</option>
                          <option value="__standard__">Standaard gebruiken</option>
                          {locationOptions.map((location) => <option key={location.id} value={location.id}>{location.label}</option>)}
                        </select>
                      </td>'''
new_table = '''                      <td onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
                        <button
                          type="button"
                          className="rz-input rz-store-select"
                          disabled={busyLineId === line.id || isProcessingBatch || isViewer}
                          aria-label={`Locatie voor ${line.article_name_raw}`}
                          data-testid={`receipt-line-location-select-${line.id}`}
                          onClick={() => openLocationPicker(line.id, 'handling')}
                          style={{ width: '100%', textAlign: 'left', cursor: busyLineId === line.id || isProcessingBatch || isViewer ? 'not-allowed' : 'pointer' }}
                        >
                          {locationLabelForDraft(entry.draft) || 'Kies locatie'}
                        </button>
                      </td>'''
if text.count(old_table) != 1:
    raise SystemExit(f'STOP: table location control count={text.count(old_table)}')
text = text.replace(old_table, new_table, 1)

old_invalid = '''      if (!isDirect && !selectedLocation) {
        throw new Error('Kies een geldige locatie en sublocatie.')
      }

      await persistLocationHandlingChoice({
        entry,
        nextOverride,
        nextLocationId: String(nextValue || ''),
        previousOverride,
        previousLocationId,
      })'''
new_invalid = '''      if (!nextValue) {
        await persistLocationHandlingChoice({
          entry,
          nextOverride: STOCK,
          nextLocationId: '',
          previousOverride,
          previousLocationId,
        })
        return
      }

      if (!isDirect && !selectedLocation) {
        throw new Error('Kies een geldige locatie en sublocatie.')
      }

      await persistLocationHandlingChoice({
        entry,
        nextOverride,
        nextLocationId: String(nextValue || ''),
        previousOverride,
        previousLocationId,
      })'''
if text.count(old_invalid) != 1:
    raise SystemExit(f'STOP: handleLocationChoice anchor count={text.count(old_invalid)}')
text = text.replace(old_invalid, new_invalid, 1)

single_anchor = '''    const pickerEntry = lineUiStates.find((entry) => String(entry.line.id) === String(locationPickerLineId))
    if (!pickerEntry) {
      closeLocationPicker()
      return
    }

    const hasArticle = Boolean(String(pickerEntry.draft?.articleId || pickerEntry.line?.matched_household_article_id || '').trim())'''
single_repl = '''    const pickerEntry = lineUiStates.find((entry) => String(entry.line.id) === String(locationPickerLineId))
    if (!pickerEntry) {
      closeLocationPicker()
      return
    }

    if (locationPickerSaveMode === 'handling') {
      await handleLocationChoice(pickerEntry, nextLocationId)
      closeLocationPicker()
      return
    }

    const hasArticle = Boolean(String(pickerEntry.draft?.articleId || pickerEntry.line?.matched_household_article_id || '').trim())'''
if text.count(single_anchor) != 1:
    raise SystemExit(f'STOP: picker single routing anchor count={text.count(single_anchor)}')
text = text.replace(single_anchor, single_repl, 1)

actions_anchor = '''                  <div className="rz-modal-actions">
                    {canManageLocations ? ('''
actions_repl = '''                  <div className="rz-modal-actions">
                    {locationPickerMode === 'single' && locationPickerSaveMode === 'handling' ? (
                      <Button
                        variant="secondary"
                        type="button"
                        disabled={pickerLineBusy}
                        onClick={async () => {
                          const pickerEntry = lineUiStates.find((entry) => String(entry.line.id) === String(locationPickerLineId))
                          if (!pickerEntry) return
                          await handleLocationChoice(pickerEntry, '__standard__')
                          closeLocationPicker()
                        }}
                        data-testid="receipt-location-use-standard"
                      >
                        Standaard gebruiken
                      </Button>
                    ) : null}
                    {canManageLocations ? ('''
if text.count(actions_anchor) != 1:
    raise SystemExit(f'STOP: picker actions anchor count={text.count(actions_anchor)}')
text = text.replace(actions_anchor, actions_repl, 1)
product.write_text(text, encoding='utf-8', newline='\n')

# Correct the B3 source contract: protect handling semantics without requiring the regressive table <select>.
b3 = Path('frontend/src/features/stores/StoreBatchDetailPage.b3-native.contract.test.js')
b3_text = b3.read_text(encoding='utf-8')
old_b3 = "    expect(source).toContain('handleLocationChoice(entry, event.target.value)')"
new_b3 = "    expect(source).toContain(\"openLocationPicker(line.id, 'handling')\")\n    expect(source).toContain(\"locationPickerSaveMode === 'handling'\")\n    expect(source).toContain('handleLocationChoice(pickerEntry, nextLocationId)')"
if b3_text.count(old_b3) != 1:
    raise SystemExit(f'STOP: B3 contract anchor count={b3_text.count(old_b3)}')
b3.write_text(b3_text.replace(old_b3, new_b3, 1), encoding='utf-8', newline='\n')

# Strengthen the executable pytest source contract with the restored table-picker and B3 routing invariants.
backend_contract = Path('backend/tests/test_uitpakken_location_admin_contract.py')
contract_text = backend_contract.read_text(encoding='utf-8')
append_block = '''\n\ndef test_uitpakken_receipt_table_opens_picker_and_preserves_b3_location_handling():
    text = UITPAKKEN.read_text(encoding="utf-8")
    assert "openLocationPicker(line.id, 'handling')" in text
    assert "locationPickerSaveMode === 'handling'" in text
    assert "await handleLocationChoice(pickerEntry, nextLocationId)" in text
    assert "await handleLocationChoice(pickerEntry, '__standard__')" in text
    assert "nextOverride: STOCK" in text
    assert "nextLocationId: ''" in text
'''
if 'def test_uitpakken_receipt_table_opens_picker_and_preserves_b3_location_handling' not in contract_text:
    backend_contract.write_text(contract_text.rstrip() + append_block + '\n', encoding='utf-8', newline='\n')

# Runtime regression: prove main table opens the dialog, Admin create applies through STOCK handling,
# and a member really has the picker open while management controls remain absent.
test = Path('frontend/tests/e2e/uitpakken-admin-location-create.frontend-regression.spec.js')
s = test.read_text(encoding='utf-8')
test_replacements = [
    ('''    targetLocationWrites: [],\n  };''', '''    targetLocationWrites: [],\n    handlingOverrideWrites: [],\n  };'''),
    ('''      const body = request.postDataJSON();\n      return json({ inventory_handling_override: body.inventory_handling_override });''', '''      const body = request.postDataJSON();\n      state.handlingOverrideWrites.push(body);\n      return json({ inventory_handling_override: body.inventory_handling_override });'''),
    ('''    await expect(locationButton).toBeVisible();\n    await locationButton.click();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();''', '''    await expect(locationButton).toBeVisible();\n    expect(await locationButton.evaluate((element) => element.tagName)).toBe('BUTTON');\n    await locationButton.click();\n\n    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();\n    await expect(page.getByTestId('receipt-location-use-standard')).toBeVisible();\n    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();'''),
    ('''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('space-2');\n    await expect(locationButton).toContainText('Garage');''', '''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('space-2');\n    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');\n    await expect(locationButton).toContainText('Garage');'''),
    ('''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('sublocation-1');\n    await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toContainText('Keuken / Voorraadkast');''', '''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('sublocation-1');\n    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');\n    await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toContainText('Keuken / Voorraadkast');'''),
    ('''    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toHaveCount(0);''', '''    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();\n    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toHaveCount(0);'''),
]
for old, new in test_replacements:
    if s.count(old) != 1:
        raise SystemExit(f'STOP: e2e anchor count={s.count(old)} for {old[:60]!r}')
    s = s.replace(old, new, 1)
test.write_text(s, encoding='utf-8', newline='\n')

print('PASS: scoped picker restoration applied; detail and bulk picker flows preserved')
