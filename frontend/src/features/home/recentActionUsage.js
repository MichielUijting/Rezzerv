const RECENT_ACTION_STORAGE_PREFIX = 'inhuis_recent_actions_v1'
const DEFAULT_RECENT_ACTION_LIMIT = 4

export const ACTION_ROUTE_BY_KEY = Object.freeze({
  meldingen: '/meldingen',
  'bijna-op': '/bijna-op',
  winkelen: '/winkelen',
  voorraad: '/voorraad',
  productgroepen: '/productgroepen',
  kassabonnen: '/kassabonnen',
  kassa: '/kassa',
  spaartegoeden: '/spaartegoeden',
  'externe-databases': '/externe-databases',
  catalogus: '/catalogus',
  instellingen: '/instellingen',
  locaties: '/instellingen/locaties',
  admin: '/admin',
  superuser: '/superuser',
})

function storageFor(windowLike = typeof window !== 'undefined' ? window : null) {
  try {
    return windowLike?.localStorage || null
  } catch {
    return null
  }
}

function userStorageKey(context) {
  const userId = String(context?.user_id || '').trim()
  return userId ? `${RECENT_ACTION_STORAGE_PREFIX}:${userId}` : ''
}

export function readRecentActionKeys(context, windowLike) {
  const key = userStorageKey(context)
  const storage = storageFor(windowLike)
  if (!key || !storage) return []
  try {
    const parsed = JSON.parse(storage.getItem(key) || '[]')
    if (!Array.isArray(parsed)) return []
    const seen = new Set()
    return parsed
      .map((value) => String(value || '').trim())
      .filter((value) => {
        if (!value || !ACTION_ROUTE_BY_KEY[value] || seen.has(value)) return false
        seen.add(value)
        return true
      })
      .slice(0, DEFAULT_RECENT_ACTION_LIMIT)
  } catch {
    return []
  }
}

export function recordRecentAction(actionKey, context, windowLike) {
  const normalizedKey = String(actionKey || '').trim()
  const storageKey = userStorageKey(context)
  const storage = storageFor(windowLike)
  if (!normalizedKey || !ACTION_ROUTE_BY_KEY[normalizedKey] || !storageKey || !storage) return []
  const next = [
    normalizedKey,
    ...readRecentActionKeys(context, windowLike).filter((key) => key !== normalizedKey),
  ].slice(0, DEFAULT_RECENT_ACTION_LIMIT)
  try {
    storage.setItem(storageKey, JSON.stringify(next))
  } catch {}
  return next
}

export function selectRecentActionTiles({
  recentKeys = [],
  availableTiles = [],
  excludeKeys = [],
  limit = DEFAULT_RECENT_ACTION_LIMIT,
} = {}) {
  const excluded = new Set(excludeKeys.map((key) => String(key || '').trim()).filter(Boolean))
  const byKey = new Map(
    availableTiles
      .filter((tile) => tile?.key && ACTION_ROUTE_BY_KEY[tile.key] && !excluded.has(String(tile.key)))
      .map((tile) => [String(tile.key), tile]),
  )
  const selected = []
  const seen = new Set()

  for (const key of recentKeys) {
    const tile = byKey.get(String(key))
    if (!tile || seen.has(tile.key)) continue
    selected.push(tile)
    seen.add(tile.key)
    if (selected.length >= limit) return selected
  }

  for (const tile of availableTiles) {
    if (!tile?.key || excluded.has(String(tile.key)) || seen.has(tile.key) || !ACTION_ROUTE_BY_KEY[tile.key]) continue
    selected.push(tile)
    seen.add(tile.key)
    if (selected.length >= limit) break
  }

  return selected
}
