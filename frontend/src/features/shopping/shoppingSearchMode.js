const STORAGE_PREFIX = 'inhuis-shopping-search-mode'

export const DEFAULT_SHOPPING_SEARCH_MODE = 'specific'

export const SHOPPING_SEARCH_MODE_OPTIONS = Object.freeze([
  { value: 'specific', label: 'Specifiek' },
  { value: 'generic', label: 'Generiek' },
])

function normalizeMode(value) {
  return value === 'generic' ? 'generic' : DEFAULT_SHOPPING_SEARCH_MODE
}

function userStorageKey(context) {
  const userId = String(context?.user_id || context?.email || '').trim().toLowerCase()
  return userId ? `${STORAGE_PREFIX}:${userId}` : ''
}

export function readShoppingSearchModePreference(context) {
  const key = userStorageKey(context)
  if (!key || typeof window === 'undefined') return DEFAULT_SHOPPING_SEARCH_MODE
  try {
    return normalizeMode(window.localStorage.getItem(key))
  } catch {
    return DEFAULT_SHOPPING_SEARCH_MODE
  }
}

export function writeShoppingSearchModePreference(mode, context) {
  const normalized = normalizeMode(mode)
  const key = userStorageKey(context)
  if (!key || typeof window === 'undefined') return normalized
  try {
    window.localStorage.setItem(key, normalized)
  } catch {}
  return normalized
}

export function shoppingSearchScopes(mode) {
  return normalizeMode(mode) === 'generic'
    ? ['product_types', 'article_groups']
    : ['global_products', 'household_articles']
}

export function combineShoppingSearchResults(payloads, limit = 5) {
  const combined = []
  const seen = new Set()
  for (const payload of payloads || []) {
    for (const item of payload?.items || []) {
      const key = `${String(item?.source_type || '')}:${String(item?.source_id || item?.label || '')}`
      if (seen.has(key)) continue
      seen.add(key)
      combined.push(item)
      if (combined.length >= limit) return combined
    }
  }
  return combined
}
