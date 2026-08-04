import { describe, expect, it } from 'vitest'
import {
  DIRECT_CONSUMPTION,
  INVENTORY_HANDLING_OPTIONS,
  STOCK,
} from './InventoryHandlingField.jsx'

describe('InventoryHandlingField B1 contract', () => {
  it('keeps existing household articles on STOCK by default', () => {
    expect(STOCK).toBe('STOCK')
    expect(INVENTORY_HANDLING_OPTIONS[0]).toEqual({
      value: STOCK,
      label: 'Opslaan in voorraad',
    })
  })

  it('offers the explicit direct-consumption choice', () => {
    expect(DIRECT_CONSUMPTION).toBe('DIRECT_CONSUMPTION')
    expect(INVENTORY_HANDLING_OPTIONS).toContainEqual({
      value: DIRECT_CONSUMPTION,
      label: 'Direct consumeren',
    })
  })

  it('does not introduce any third or ambiguous handling mode', () => {
    expect(INVENTORY_HANDLING_OPTIONS.map((option) => option.value)).toEqual([
      STOCK,
      DIRECT_CONSUMPTION,
    ])
  })
})
