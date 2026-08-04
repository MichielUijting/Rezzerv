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

async function readJsonResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || fallbackMessage)
  }
  return data
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
  const data = await readJsonResponse(response, 'Standaardverwerking kon niet worden geladen.')

  return Object.fromEntries(
    (Array.isArray(data?.items) ? data.items : []).map((item) => [
      String(item.id),
      inventoryHandlingPresentation(item.default_inventory_handling),
    ]),
  )
}

export async function fetchInventoryHandlingOverridesByLineIds(householdId, purchaseImportLineIds) {
  const normalizedHouseholdId = String(householdId || '').trim()
  if (!normalizedHouseholdId) throw new Error('Geen actief huishouden beschikbaar.')

  const uniqueLineIds = Array.from(new Set(
    (Array.isArray(purchaseImportLineIds) ? purchaseImportLineIds : [])
      .map((value) => String(value || '').trim())
      .filter(Boolean),
  ))
  if (uniqueLineIds.length === 0) return {}

  const response = await fetchJsonWithAuth(
    `/api/households/${encodeURIComponent(normalizedHouseholdId)}/purchase-import-lines/inventory-handling-overrides/batch`,
    {
      method: 'POST',
      body: JSON.stringify({ purchase_import_line_ids: uniqueLineIds }),
    },
  )
  const data = await readJsonResponse(response, 'Regelafwijkingen konden niet worden geladen.')
  return Object.fromEntries(
    (Array.isArray(data?.items) ? data.items : []).map((item) => [
      String(item.purchase_import_line_id),
      normalizeInventoryHandlingOverride(item.inventory_handling_override),
    ]),
  )
}

export async function saveInventoryHandlingOverride(householdId, purchaseImportLineId, value) {
  const normalizedHouseholdId = String(householdId || '').trim()
  const normalizedLineId = String(purchaseImportLineId || '').trim()
  if (!normalizedHouseholdId) throw new Error('Geen actief huishouden beschikbaar.')
  if (!normalizedLineId) throw new Error('Geen bonregel beschikbaar.')

  const response = await fetchJsonWithAuth(
    `/api/households/${encodeURIComponent(normalizedHouseholdId)}/purchase-import-lines/${encodeURIComponent(normalizedLineId)}/inventory-handling-override`,
    {
      method: 'PUT',
      body: JSON.stringify({
        inventory_handling_override: normalizeInventoryHandlingOverride(value),
      }),
    },
  )
  const data = await readJsonResponse(response, 'Regelafwijking kon niet worden opgeslagen.')
  return normalizeInventoryHandlingOverride(data?.inventory_handling_override)
}
