import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./StoreBatchDetailPage.jsx', import.meta.url), 'utf8')

describe('B3 native Uitpakken integration contract', () => {
  it('renders Verwerking as a native column in the existing Rezzerv table', () => {
    expect(source).toContain("{ key: 'verwerking', width: 250 }")
    expect(source).toContain('columnKey="verwerking"')
    expect(source).toContain('>Verwerking</ResizableHeaderCell>')
    expect(source).toContain('lineColumnWidths.verwerking')
    expect(source).toContain('colSpan={6}')
  })

  it('uses the shared B3 selector and persists changes immediately', () => {
    expect(source).toContain("import InventoryHandlingOverrideSelect from '../receipts/InventoryHandlingOverrideSelect.jsx'")
    expect(source).toContain('<InventoryHandlingOverrideSelect')
    expect(source).toContain('handleInventoryHandlingOverrideChange(entry, nextOverride)')
    expect(source).toContain('saveInventoryHandlingOverride(householdId, lineId, nextOverride)')
  })

  it('loads defaults and saved line overrides for the active household', () => {
    expect(source).toContain('fetchInventoryHandlingByArticleIds(householdId, articleIds)')
    expect(source).toContain('fetchInventoryHandlingOverridesByLineIds(householdId, lineIds)')
    expect(source).toContain('inventoryHandlingByArticleId[articleId]')
    expect(source).toContain('inventoryHandlingOverridesByLineId[String(line.id)]')
  })

  it('keeps Direct consumption bound to Direct / Direct and locks normal location editing', () => {
    expect(source).toContain("String(location?.label || '').trim().toLowerCase() === 'direct / direct'")
    expect(source).toContain('presentation.handling === DIRECT_CONSUMPTION')
    expect(source).toContain('entry.inventoryHandling?.handling === DIRECT_CONSUMPTION')
    expect(source).toContain("await persistLineDraft(entry.line, { locationId: '' }")
  })

  it('does not introduce portal or DOM injection architecture', () => {
    expect(source).not.toContain('createPortal')
    expect(source).not.toContain('MutationObserver')
    expect(source).not.toContain('document.querySelector')
    expect(source).not.toContain('appendChild(')
  })
})
