import { describe, expect, it } from 'vitest'
import {
  buildActiveLocationOptions,
  buildSelectableLocationIds,
  isLocationSelectionValid,
  LOCATION_EXACT,
  LOCATION_GLOBAL,
  LOCATION_NONE,
} from './unpackingLocationPolicy.js'

const spacesData = {
  items: [
    { id: 'space-b', naam: 'Berging', active: true },
    { id: 'space-k', naam: 'Keuken', active: true },
    { id: 'space-old', naam: 'Oud', active: false },
  ],
}

const sublocationsData = {
  items: [
    { id: 'sub-kast', naam: 'Kast', space_id: 'space-k', active: true },
    { id: 'sub-old', naam: 'Oude plank', space_id: 'space-k', active: false },
  ],
}

describe('Uitpakken location policy', () => {
  it('shows no location choices when location tracking is disabled', () => {
    expect(buildActiveLocationOptions(spacesData, sublocationsData, LOCATION_NONE)).toEqual([])
  })

  it('offers only main spaces for global location tracking', () => {
    const options = buildActiveLocationOptions(spacesData, sublocationsData, LOCATION_GLOBAL)
    expect(options.map((item) => item.id)).toEqual(['space-b', 'space-k'])
    expect(options.every((item) => item.type === 'space')).toBe(true)
    expect(options.every((item) => item.has_sublocations === false)).toBe(true)
  })

  it('preserves the room-to-sublocation choice for exact location tracking', () => {
    const options = buildActiveLocationOptions(spacesData, sublocationsData, LOCATION_EXACT)
    expect(options.find((item) => item.id === 'space-k')?.has_sublocations).toBe(true)
    expect(options.find((item) => item.id === 'sub-kast')).toMatchObject({
      type: 'sublocation',
      space_id: 'space-k',
      sublocation_id: 'sub-kast',
      label: 'Keuken / Kast',
    })
  })

  it('treats locationless lines as ready without a synthetic location', () => {
    const selectable = buildSelectableLocationIds([])
    expect(isLocationSelectionValid(LOCATION_NONE, '', selectable)).toBe(true)
    expect(isLocationSelectionValid(LOCATION_NONE, 'legacy-direct', selectable)).toBe(true)
  })

  it('only treats selectable global/exact targets as ready', () => {
    const exactOptions = buildActiveLocationOptions(spacesData, sublocationsData, LOCATION_EXACT)
    const exactSelectable = buildSelectableLocationIds(exactOptions)
    expect(isLocationSelectionValid(LOCATION_EXACT, 'space-k', exactSelectable)).toBe(false)
    expect(isLocationSelectionValid(LOCATION_EXACT, 'sub-kast', exactSelectable)).toBe(true)
    expect(isLocationSelectionValid(LOCATION_EXACT, 'space-b', exactSelectable)).toBe(true)

    const globalOptions = buildActiveLocationOptions(spacesData, sublocationsData, LOCATION_GLOBAL)
    const globalSelectable = buildSelectableLocationIds(globalOptions)
    expect(isLocationSelectionValid(LOCATION_GLOBAL, 'space-k', globalSelectable)).toBe(true)
    expect(isLocationSelectionValid(LOCATION_GLOBAL, 'sub-kast', globalSelectable)).toBe(false)
  })
})
