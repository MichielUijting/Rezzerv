import { describe, expect, it } from 'vitest'
import {
  DIRECT_CONSUMPTION,
  DIRECT_LOCATION,
  DIRECT_SUBLOCATION,
  STOCK,
  inventoryHandlingLabel,
  inventoryHandlingPresentation,
  normalizeInventoryHandling,
} from './dayArticleHandling.js'

describe('Release B2 Uitpakken-presentatie', () => {
  it('valt veilig terug op STOCK', () => {
    expect(normalizeInventoryHandling(undefined)).toBe(STOCK)
    expect(normalizeInventoryHandling('onbekend')).toBe(STOCK)
    expect(inventoryHandlingLabel(undefined)).toBe('Opslaan in voorraad')
  })

  it('toont direct consumeren met beschermde bestemming Direct / Direct', () => {
    expect(inventoryHandlingPresentation(DIRECT_CONSUMPTION)).toEqual({
      handling: DIRECT_CONSUMPTION,
      label: 'Direct consumeren',
      location: DIRECT_LOCATION,
      sublocation: DIRECT_SUBLOCATION,
    })
  })

  it('overschrijft bij STOCK geen bestaande locatie of sublocatie', () => {
    expect(inventoryHandlingPresentation(STOCK)).toEqual({
      handling: STOCK,
      label: 'Opslaan in voorraad',
      location: null,
      sublocation: null,
    })
  })
})
