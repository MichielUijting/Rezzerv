import { sortOptionObjects } from '../../ui/sorting'

export const LOCATION_NONE = 'none'
export const LOCATION_GLOBAL = 'global'
export const LOCATION_EXACT = 'exact'

function normalizeLocationTrackingLevel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if ([LOCATION_NONE, LOCATION_GLOBAL, LOCATION_EXACT].includes(normalized)) return normalized
  return LOCATION_EXACT
}

export function buildSelectableLocationIds(locationOptions) {
  return new Set(
    (locationOptions || [])
      .filter((location) => location?.type === 'sublocation' || !location?.has_sublocations)
      .map((location) => String(location?.id || ''))
      .filter(Boolean),
  )
}

export function isLocationSelectionValid(
  locationTrackingLevel,
  locationId,
  selectableLocationIds,
) {
  const level = normalizeLocationTrackingLevel(locationTrackingLevel)
  if (level === LOCATION_NONE) return true

  const normalizedLocationId = String(locationId || '').trim()
  if (!normalizedLocationId) return false
  return selectableLocationIds.has(normalizedLocationId)
}

export function buildActiveLocationOptions(
  spacesData,
  sublocationsData,
  locationTrackingLevel = LOCATION_EXACT,
) {
  const level = normalizeLocationTrackingLevel(locationTrackingLevel)
  if (level === LOCATION_NONE) return []

  const activeSpaces = Array.isArray(spacesData?.items)
    ? spacesData.items.filter((item) => Boolean(item?.active))
    : []
  const activeSublocations = level === LOCATION_EXACT && Array.isArray(sublocationsData?.items)
    ? sublocationsData.items.filter((item) => Boolean(item?.active))
    : []
  const sublocationsBySpaceId = new Map()

  activeSublocations.forEach((item) => {
    const key = String(item?.space_id || '')
    if (!key) return
    const current = sublocationsBySpaceId.get(key) || []
    current.push(item)
    sublocationsBySpaceId.set(key, current)
  })

  const rows = []
  sortOptionObjects(activeSpaces, (space) => space?.naam || '').forEach((space) => {
    const spaceId = String(space?.id || '')
    const spaceName = String(space?.naam || '').trim()
    if (!spaceId || !spaceName) return

    const linked = sortOptionObjects(
      sublocationsBySpaceId.get(spaceId) || [],
      (item) => item?.naam || '',
    )
    rows.push({
      id: spaceId,
      label: spaceName,
      type: 'space',
      space_id: spaceId,
      sublocation_id: '',
      has_sublocations: linked.length > 0,
    })

    linked.forEach((sublocation) => {
      const sublocationId = String(sublocation?.id || '')
      const sublocationName = String(sublocation?.naam || '').trim()
      if (!sublocationId || !sublocationName) return
      rows.push({
        id: sublocationId,
        label: `${spaceName} / ${sublocationName}`,
        type: 'sublocation',
        space_id: spaceId,
        sublocation_id: sublocationId,
        parent_label: spaceName,
        sublocation_label: sublocationName,
        has_sublocations: false,
      })
    })
  })

  return sortOptionObjects(rows, (location) => location?.label || '')
}
