import { fetchJsonWithAuth } from '../../lib/authSession'

export const STOCK = 'STOCK'
export const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'
export const DIRECT_LOCATION = 'Direct'
export const DIRECT_SUBLOCATION = 'Direct'

const HANDLING_CACHE_TTL_MS = 60_000
const articleHandlingCache = new Map()
const lineOverrideCache = new Map()

function cacheKey(householdId, objectId) {
  return `${String(householdId || '').trim()}::${String(objectId || '').trim()}`
}

function readHandlingCache(cache, key) {
  const entry = cache.get(key)
  if (!entry) return { hit: false, value: null }
  if (entry.expiresAt <= Date.now()) {
    cache.delete(key)
    return { hit: false, value: null }
  }
  return { hit: true, value: entry.value }
}

function writeHandlingCache(cache, key, value) {
  cache.set(key, {
    expiresAt: Date.now() + HANDLING_CACHE_TTL_MS,
    value,
  })
}

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

export function resolveEffectiveLineDestination({
  defaultHandling,
  lineOverride = null,
  currentLocationId = '',
  directLocationId = '',
}) {
  const presentation = lineInventoryHandlingPresentation(defaultHandling, lineOverride)
  const normalizedCurrentLocationId = String(currentLocationId || '')
  const normalizedDirectLocationId = String(directLocationId || '')

  if (presentation.handling === DIRECT_CONSUMPTION) {
    return {
      ...presentation,
      locationId: normalizedDirectLocationId,
      requiresLocationChange: Boolean(normalizedDirectLocationId)
        && normalizedCurrentLocationId !== normalizedDirectLocationId,
    }
  }

  const locationId = normalizedCurrentLocationId === normalizedDirectLocationId
    ? ''
    : normalizedCurrentLocationId
  return {
    ...presentation,
    locationId,
    requiresLocationChange: locationId !== normalizedCurrentLocationId,
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

  const result = {}
  const missingArticleIds = []
  uniqueArticleIds.forEach((articleId) => {
    const cached = readHandlingCache(articleHandlingCache, cacheKey(normalizedHouseholdId, articleId))
    if (cached.hit) {
      result[articleId] = cached.value
    } else {
      missingArticleIds.push(articleId)
    }
  })

  if (missingArticleIds.length > 0) {
    const response = await fetchJsonWithAuth(
      `/api/households/${encodeURIComponent(normalizedHouseholdId)}/articles/inventory-handling/batch`,
      {
        method: 'POST',
        body: JSON.stringify({ household_article_ids: missingArticleIds }),
      },
    )
    const data = await readJsonResponse(response, 'Directe consumptie kon niet worden geladen.')

    ;(Array.isArray(data?.items) ? data.items : []).forEach((item) => {
      const articleId = String(item.id)
      const presentation = inventoryHandlingPresentation(item.default_inventory_handling)
      result[articleId] = presentation
      writeHandlingCache(articleHandlingCache, cacheKey(normalizedHouseholdId, articleId), presentation)
    })
  }

  return result
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

  const result = {}
  const missingLineIds = []
  uniqueLineIds.forEach((lineId) => {
    const cached = readHandlingCache(lineOverrideCache, cacheKey(normalizedHouseholdId, lineId))
    if (cached.hit) {
      result[lineId] = cached.value
    } else {
      missingLineIds.push(lineId)
    }
  })

  if (missingLineIds.length > 0) {
    const response = await fetchJsonWithAuth(
      `/api/households/${encodeURIComponent(normalizedHouseholdId)}/purchase-import-lines/inventory-handling-overrides/batch`,
      {
        method: 'POST',
        body: JSON.stringify({ purchase_import_line_ids: missingLineIds }),
      },
    )
    const data = await readJsonResponse(response, 'Regelafwijkingen konden niet worden geladen.')
    ;(Array.isArray(data?.items) ? data.items : []).forEach((item) => {
      const lineId = String(item.purchase_import_line_id)
      const normalizedOverride = normalizeInventoryHandlingOverride(item.inventory_handling_override)
      result[lineId] = normalizedOverride
      writeHandlingCache(lineOverrideCache, cacheKey(normalizedHouseholdId, lineId), normalizedOverride)
    })
  }

  return result
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
  const normalizedOverride = normalizeInventoryHandlingOverride(data?.inventory_handling_override)
  writeHandlingCache(lineOverrideCache, cacheKey(normalizedHouseholdId, normalizedLineId), normalizedOverride)
  return normalizedOverride
}
