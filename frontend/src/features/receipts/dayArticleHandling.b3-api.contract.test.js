import { describe, expect, it } from 'vitest'
import {
  fetchInventoryHandlingOverridesByLineIds,
  saveInventoryHandlingOverride,
} from './dayArticleHandling'


describe('B3 line override API contract', () => {
  it('exports batch loading and save functions', () => {
    expect(typeof fetchInventoryHandlingOverridesByLineIds).toBe('function')
    expect(typeof saveInventoryHandlingOverride).toBe('function')
  })

  it('keeps the API household and line scoped', async () => {
    const source = await import('./dayArticleHandling?raw')
    const text = String(source.default || '')

    expect(text).toContain('/purchase-import-lines/inventory-handling-overrides/batch')
    expect(text).toContain('/purchase-import-lines/${encodeURIComponent(normalizedLineId)}/inventory-handling-override')
    expect(text).toContain('inventory_handling_override')
    expect(text).toContain("method: 'PUT'")
  })
})
