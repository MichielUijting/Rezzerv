import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

let availability = null
let loadPromise = null
const listeners = new Set()

function publish(nextAvailability) {
  availability = nextAvailability
  for (const listener of listeners) listener(availability)
}

async function loadAvailability({ force = false } = {}) {
  if (!force && availability) return availability
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    try {
      const response = await fetchJsonWithAuth('/api/action-buttons')
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Acties op de Startpagina konden niet worden geladen.')
      const next = Object.fromEntries(
        (payload.items || [])
          .filter((item) => item?.home_tile_key)
          .map((item) => [String(item.home_tile_key), Boolean(item.enabled)]),
      )
      publish(next)
      return next
    } catch {
      // Home-action availability is additive to authorization. When the projection
      // is temporarily unavailable, homeNavigation falls back to each tile's
      // explicit default so existing navigation remains deterministic.
      return availability || {}
    } finally {
      loadPromise = null
    }
  })()

  return loadPromise
}

export function refreshActionButtonAvailability() {
  return loadAvailability({ force: true })
}

export function useActionButtonAvailability({ enabled = true } = {}) {
  const [snapshot, setSnapshot] = useState(() => (enabled ? availability || {} : {}))

  useEffect(() => {
    if (!enabled) {
      setSnapshot({})
      return undefined
    }

    const listener = (next) => setSnapshot(next || {})
    listeners.add(listener)
    setSnapshot(availability || {})
    void loadAvailability()

    const refresh = () => { void refreshActionButtonAvailability() }
    window.addEventListener('focus', refresh)
    window.addEventListener('rezzerv-action-buttons-changed', refresh)
    const timer = window.setInterval(refresh, 30000)
    return () => {
      listeners.delete(listener)
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('rezzerv-action-buttons-changed', refresh)
    }
  }, [enabled])

  return snapshot
}
