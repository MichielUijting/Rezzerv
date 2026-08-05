import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const source = fs.readFileSync(path.resolve('src/features/stores/StoreBatchDetailPage.jsx'), 'utf8')

describe('B3 location-only native contract', () => {
  it('uses Locatie as the only visible B3 control', () => {
    expect(source).not.toContain('columnKey=\"verwerking\"')
    expect(source).not.toContain('<InventoryHandlingOverrideSelect')
    expect(source).toContain('Standaard gebruiken')
    expect(source).toContain('handleLocationChoice(entry, event.target.value)')
  })
  it('maps Direct / Direct and normal locations to the correct temporary handling', () => {
    expect(source).toContain('isDirect ? DIRECT_CONSUMPTION : STOCK')
    expect(source).toContain('saveInventoryHandlingOverride(householdId, lineId, null)')
    expect(source).toContain("defaultLocationPolicy: 'line_only'")
  })
  it('stores location and temporary handling as one recoverable user action', () => {
    expect(source).toContain('async function persistLocationHandlingChoice')
    expect(source).toContain('previousOverride')
    expect(source).toContain('previousLocationId')
    expect(source).toContain('if (overrideSaved)')
    expect(source).toContain('restoredOverride')
    expect(source).toContain('await refreshBatch(batch?.batch_id)')
  })

})
