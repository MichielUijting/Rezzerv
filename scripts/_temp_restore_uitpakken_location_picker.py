from pathlib import Path

product = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
text = product.read_text(encoding='utf-8')

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
                          onClick={() => openLocationPicker(line.id)}
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

old_single = '''    const hasArticle = Boolean(String(pickerEntry.draft?.articleId || pickerEntry.line?.matched_household_article_id || '').trim())

    if (hasArticle && nextLocationId) {
      setPendingDefaultLocationChoice({
        lineId: pickerEntry.line.id,
        locationId: nextLocationId,
      })
      closeLocationPicker()
      return
    }

    await persistLineDraft(
      pickerEntry.line,
      { locationId: nextLocationId },
      { defaultLocationPolicy: 'line_only' }
    )
    closeLocationPicker()'''
new_single = '''    await handleLocationChoice(pickerEntry, nextLocationId)
    closeLocationPicker()'''
if text.count(old_single) != 1:
    raise SystemExit(f'STOP: picker single-save anchor count={text.count(old_single)}')
text = text.replace(old_single, new_single, 1)

old_actions = '''                  <div className="rz-modal-actions">
                    {canManageLocations ? ('''
new_actions = '''                  <div className="rz-modal-actions">
                    {locationPickerMode === 'single' ? (
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
if text.count(old_actions) != 1:
    raise SystemExit(f'STOP: picker actions anchor count={text.count(old_actions)}')
text = text.replace(old_actions, new_actions, 1)
product.write_text(text, encoding='utf-8', newline='\n')

test = Path('frontend/tests/e2e/uitpakken-admin-location-create.frontend-regression.spec.js')
s = test.read_text(encoding='utf-8')
replacements = [
    ('''    targetLocationWrites: [],\n  };''', '''    targetLocationWrites: [],\n    handlingOverrideWrites: [],\n  };'''),
    ('''      const body = request.postDataJSON();\n      return json({ inventory_handling_override: body.inventory_handling_override });''', '''      const body = request.postDataJSON();\n      state.handlingOverrideWrites.push(body);\n      return json({ inventory_handling_override: body.inventory_handling_override });'''),
    ('''    await expect(locationButton).toBeVisible();\n    await locationButton.click();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();''', '''    await expect(locationButton).toBeVisible();\n    expect(await locationButton.evaluate((element) => element.tagName)).toBe('BUTTON');\n    await locationButton.click();\n\n    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();\n    await expect(page.getByTestId('receipt-location-use-standard')).toBeVisible();\n    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();'''),
    ('''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('space-2');\n    await expect(locationButton).toContainText('Garage');''', '''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('space-2');\n    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');\n    await expect(locationButton).toContainText('Garage');'''),
    ('''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('sublocation-1');\n    await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toContainText('Keuken / Voorraadkast');''', '''    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('sublocation-1');\n    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');\n    await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toContainText('Keuken / Voorraadkast');'''),
    ('''    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toHaveCount(0);''', '''    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();\n    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();\n\n    await expect(page.getByTestId('receipt-location-create-space')).toHaveCount(0);'''),
]
for old, new in replacements:
    if s.count(old) != 1:
        raise SystemExit(f'STOP: test anchor count={s.count(old)} for {old[:60]!r}')
    s = s.replace(old, new, 1)
test.write_text(s, encoding='utf-8', newline='\n')
print('PASS: picker restoration applied')
