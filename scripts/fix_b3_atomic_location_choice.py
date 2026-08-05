from pathlib import Path
import re

page_path = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
test_path = Path('frontend/src/features/stores/StoreBatchDetailPage.b3-native.contract.test.js')
source = page_path.read_text(encoding='utf-8')

pattern = re.compile(r"\n  async function handleLocationChoice\(entry, nextValue\) \{.*?\n  \}\n\n  async function refreshLocationOptions", re.S)
replacement = r'''
  async function persistLocationHandlingChoice({
    entry,
    nextOverride,
    nextLocationId,
    previousOverride,
    previousLocationId,
  }) {
    const householdId = String(household?.active_household_id ?? household?.id ?? batch?.household_id ?? '').trim()
    const lineId = String(entry?.line?.id || '')
    let overrideSaved = false
    let locationSaved = false

    try {
      const savedOverride = await saveInventoryHandlingOverride(householdId, lineId, nextOverride)
      overrideSaved = true
      setInventoryHandlingOverridesByLineId((current) => ({ ...current, [lineId]: savedOverride }))

      await persistLineDraft(
        entry.line,
        { locationId: String(nextLocationId || '') },
        { defaultLocationPolicy: 'line_only', suppressSuccessFeedback: true },
      )
      locationSaved = true
      return savedOverride
    } catch (saveError) {
      if (locationSaved) {
        await persistLineDraft(
          entry.line,
          { locationId: String(previousLocationId || '') },
          { defaultLocationPolicy: 'line_only', suppressSuccessFeedback: true },
        ).catch(() => null)
      }
      if (overrideSaved) {
        const restoredOverride = await saveInventoryHandlingOverride(
          householdId,
          lineId,
          previousOverride,
        ).catch(() => previousOverride)
        setInventoryHandlingOverridesByLineId((current) => ({
          ...current,
          [lineId]: restoredOverride,
        }))
      }
      throw saveError
    }
  }

  async function handleLocationChoice(entry, nextValue) {
    const householdId = String(household?.active_household_id ?? household?.id ?? batch?.household_id ?? '').trim()
    if (!householdId) {
      showUitpakkenFeedback('error', 'Het actieve huishouden kon niet worden vastgesteld.')
      return
    }

    const lineId = String(entry?.line?.id || '')
    const previousOverride = entry.inventoryHandlingOverride || null
    const previousLocationId = String(entry?.draft?.locationId || '')
    const directLocation = directLocationOption(locationOptions)
    setBusyLineId(lineId)

    try {
      if (nextValue === '__standard__') {
        const resolution = resolveEffectiveLineDestination({
          defaultHandling: entry.defaultInventoryHandling,
          lineOverride: null,
          currentLocationId: previousLocationId,
          directLocationId: directLocation?.id || '',
        })
        if (resolution.handling === DIRECT_CONSUMPTION && !directLocation?.id) {
          throw new Error('De beschermde locatie Direct / Direct is niet beschikbaar.')
        }
        await persistLocationHandlingChoice({
          entry,
          nextOverride: null,
          nextLocationId: resolution.locationId,
          previousOverride,
          previousLocationId,
        })
        return
      }

      const selectedLocation = locationOptions.find(
        (location) => String(location.id) === String(nextValue),
      ) || null
      const isDirect = Boolean(selectedLocation && directLocationOption([selectedLocation]))
      const nextOverride = isDirect ? DIRECT_CONSUMPTION : STOCK

      if (!isDirect && !selectedLocation) {
        throw new Error('Kies een geldige locatie en sublocatie.')
      }

      await persistLocationHandlingChoice({
        entry,
        nextOverride,
        nextLocationId: String(nextValue || ''),
        previousOverride,
        previousLocationId,
      })
    } catch (handlingError) {
      const message = normalizeErrorMessage(handlingError?.message || handlingError) || 'Locatie kon niet worden opgeslagen.'
      showUitpakkenFeedback('error', message, { key: `uitpakken-location-handling-${lineId}-${Date.now()}` })
      await refreshInventoryHandling(batch, household).catch(() => null)
      await refreshBatch(batch?.batch_id).catch(() => null)
    } finally {
      setBusyLineId('')
    }
  }

  async function refreshLocationOptions'''

updated, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise SystemExit('STOP: handleLocationChoice block niet exact gevonden')

page_path.write_text(updated, encoding='utf-8')

test_source = test_path.read_text(encoding='utf-8')
extra = """
  it('stores location and temporary handling as one recoverable user action', () => {
    expect(source).toContain('async function persistLocationHandlingChoice')
    expect(source).toContain('previousOverride')
    expect(source).toContain('previousLocationId')
    expect(source).toContain('if (overrideSaved)')
    expect(source).toContain('restoredOverride')
    expect(source).toContain('await refreshBatch(batch?.batch_id)')
  })
"""
marker = '\n})\n'
if extra.strip() not in test_source:
    pos = test_source.rfind(marker)
    if pos < 0:
        raise SystemExit('STOP: contracttest-einde niet gevonden')
    test_source = test_source[:pos] + extra + test_source[pos:]
    test_path.write_text(test_source, encoding='utf-8')

print('B3_ATOMIC_LOCATION_CHOICE_REPAIR_APPLIED')
