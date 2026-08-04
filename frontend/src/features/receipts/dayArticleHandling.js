import { fetchJsonWithAuth } from '../../lib/authSession'

export const STOCK = 'STOCK'
export const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'
export const DIRECT_LOCATION = 'Direct'
export const DIRECT_SUBLOCATION = 'Direct'

export function normalizeInventoryHandling(value) {
  return String(value || '').trim().toUpperCase() === DIRECT_CONSUMPTION
    ? DIRECT_CONSUMPTION
    : STOCK
}

export function normalizeInventoryHandlingOverride(value) {
  const normalized = String(value || '').trim().toUpperCase()
  if (normalized === STOCK || normalized === DIRECT_CONSUMPTION) return normalized
  return null
}

export function effectiveInventoryHandling(defaultHandling, lineOverride = null) {
  return normalizeInventoryHandlingOverride(lineOverride)
    || normalizeInventoryHandling(defaultHandling)
}

export function inventoryHandlingLabel(value) {
  return normalizeInventoryHandling(value) === DIRECT_CONSUMPTION
    ? 'Direct consumeren'
    : 'Opslaan in voorraad'
}

export function inventoryHandlingPresentation(value) {
  const handling = normalizeInventoryHandling(value)
  if (handling === DIRECT_CONSUMPTION) {
    return {
      handling,
      label: 'Direct consumeren',
      location: DIRECT_LOCATION,
      sublocation: DIRECT_SUBLOCATION,
    }
  }
  return {
    handling,
    label: 'Opslaan in voorraad',
    location: null,
    sublocation: null,
  }
}

export function lineInventoryHandlingPresentation(defaultHandling, lineOverride = null) {
  const effectiveHandling = effectiveInventoryHandling(defaultHandling, lineOverride)
  return {
    ...inventoryHandlingPresentation(effectiveHandling),
    defaultHandling: normalizeInventoryHandling(defaultHandling),
    overrideHandling: normalizeInventoryHandlingOverride(lineOverride),
    isOverride: normalizeInventoryHandlingOverride(lineOverride) !== null,
  }
}

export async function fetchInventoryHandlingByArticleIds(householdId, householdArticleIds) {
  const normalizedHouseholdId = String(householdId || '').trim()
  if (!normalizedHouseholdId) throw new Error('Geen actief huishouden beschikbaar.')

  const uniqueArticleIds = Array.from(new Set(
    (Array.isArray(householdArticleIds) ? householdArticleIds : [])
      .map((value) => String(value || '').trim())
      .filter(Boolean),
  ))

  if (uniqueArticleIds.length === 0) return {}

  const response = await fetchJsonWithAuth(
    `/api/households/${encodeURIComponent(normalizedHouseholdId)}/articles/inventory-handling/batch`,
    {
      method: 'POST',
      body: JSON.stringify({ household_article_ids: uniqueArticleIds }),
    },
  )
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Standaardverwerking kon niet worden geladen.')
  }

  return Object.fromEntries(
    (Array.isArray(data?.items) ? data.items : []).map((item) => [
      String(item.id),
      inventoryHandlingPresentation(item.default_inventory_handling),
    ]),
  )
}
