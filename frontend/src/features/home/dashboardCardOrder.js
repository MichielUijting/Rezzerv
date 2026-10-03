const DASHBOARD_ORDER_STORAGE_PREFIX = 'inhuis_dashboard_card_order_v1'

export const DEFAULT_DASHBOARD_CARD_ORDER = Object.freeze([
  'uitgaven-vorig-jaar',
  'uitgaven',
  'winkels',
  'begroting',
])

function storageFor(windowLike = typeof window !== 'undefined' ? window : null) {
  try {
    return windowLike?.localStorage || null
  } catch {
    return null
  }
}

function storageKey(context) {
  const userId = String(context?.user_id || '').trim()
  return userId ? `${DASHBOARD_ORDER_STORAGE_PREFIX}:${userId}` : ''
}

function normalizeOrder(values) {
  const allowed = new Set(DEFAULT_DASHBOARD_CARD_ORDER)
  const seen = new Set()
  const result = []
  for (const value of Array.isArray(values) ? values : []) {
    const key = String(value || '').trim()
    if (!allowed.has(key) || seen.has(key)) continue
    seen.add(key)
    result.push(key)
  }
  for (const key of DEFAULT_DASHBOARD_CARD_ORDER) {
    if (!seen.has(key)) result.push(key)
  }
  return result
}

export function readDashboardCardOrder(context, windowLike) {
  const key = storageKey(context)
  const storage = storageFor(windowLike)
  if (!key || !storage) return [...DEFAULT_DASHBOARD_CARD_ORDER]
  try {
    return normalizeOrder(JSON.parse(storage.getItem(key) || '[]'))
  } catch {
    return [...DEFAULT_DASHBOARD_CARD_ORDER]
  }
}

export function writeDashboardCardOrder(order, context, windowLike) {
  const normalized = normalizeOrder(order)
  const key = storageKey(context)
  const storage = storageFor(windowLike)
  if (!key || !storage) return normalized
  try {
    storage.setItem(key, JSON.stringify(normalized))
  } catch {}
  return normalized
}
