import { describe, expect, it } from 'vitest'
import {
  DIRECT_CONSUMPTION,
  STOCK,
  effectiveInventoryHandling,
  lineInventoryHandlingPresentation,
  normalizeInventoryHandlingOverride,
} from './dayArticleHandling.js'

describe('Release B3 tijdelijke afwijking per bonregel', () => {
  it('gebruikt zonder regelafwijking de artikelstandaard', () => {
    expect(effectiveInventoryHandling(DIRECT_CONSUMPTION)).toBe(DIRECT_CONSUMPTION)
    expect(effectiveInventoryHandling(STOCK)).toBe(STOCK)
  })

  it('laat een regel tijdelijk afwijken naar STOCK', () => {
    expect(effectiveInventoryHandling(DIRECT_CONSUMPTION, STOCK)).toBe(STOCK)
    expect(lineInventoryHandlingPresentation(DIRECT_CONSUMPTION, STOCK)).toMatchObject({
      handling: STOCK,
      defaultHandling: DIRECT_CONSUMPTION,
      overrideHandling: STOCK,
      isOverride: true,
      location: null,
      sublocation: null,
    })
  })

  it('laat een regel tijdelijk afwijken naar DIRECT_CONSUMPTION', () => {
    expect(effectiveInventoryHandling(STOCK, DIRECT_CONSUMPTION)).toBe(DIRECT_CONSUMPTION)
    expect(lineInventoryHandlingPresentation(STOCK, DIRECT_CONSUMPTION)).toMatchObject({
      handling: DIRECT_CONSUMPTION,
      defaultHandling: STOCK,
      overrideHandling: DIRECT_CONSUMPTION,
      isOverride: true,
      location: 'Direct',
      sublocation: 'Direct',
    })
  })

  it('behandelt lege en onbekende waarden niet als geldige afwijking', () => {
    expect(normalizeInventoryHandlingOverride('')).toBeNull()
    expect(normalizeInventoryHandlingOverride('onbekend')).toBeNull()
    expect(effectiveInventoryHandling(DIRECT_CONSUMPTION, 'onbekend')).toBe(DIRECT_CONSUMPTION)
  })

  it('wijzigt de artikelstandaard niet wanneer een regel afwijkt', () => {
    const result = lineInventoryHandlingPresentation(DIRECT_CONSUMPTION, STOCK)
    expect(result.defaultHandling).toBe(DIRECT_CONSUMPTION)
    expect(result.handling).toBe(STOCK)
  })
})
