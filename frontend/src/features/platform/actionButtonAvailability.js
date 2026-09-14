import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function fetchAvailability() {
  const response = await fetchJsonWithAuth('/api/action-buttons')
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Acties op de Startpagina konden niet worden geladen.')
  return Object.fromEntries(
    (payload.items || [])
      .filter((item) => item?.home_tile_key)
      .map((item) => [String(item.home_tile_key), Boolean(item.enabled)]),
  )
}

export function refreshActionButtonAvailability() {
  window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
}

export function useActionButtonAvailability({ enabled = true } = {}) {
  const [state, setState] = useState(() => ({
    items: {},
    ready: !enabled,
  }))

  useEffect(() => {
    let active = true

    if (!enabled) {
      setState({ items: {}, ready: true })
      return () => { active = false }
    }

    async function refresh() {
      setState((current) => ({ items: current.ready ? current.items : {}, ready: false }))
      try {
        const items = await fetchAvailability()
        if (active) setState({ items, ready: true })
      } catch {
        // Availability remains additive to authorization. If the projection cannot
        // be read, fall back to the explicit product defaults after the request
        // completes rather than carrying state across users or sessions.
        if (active) setState({ items: {}, ready: true })
      }
    }

    void refresh()
    const handleRefresh = () => { void refresh() }
    window.addEventListener('focus', handleRefresh)
    window.addEventListener('rezzerv-action-buttons-changed', handleRefresh)
    const timer = window.setInterval(handleRefresh, 30000)

    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', handleRefresh)
      window.removeEventListener('rezzerv-action-buttons-changed', handleRefresh)
    }
  }, [enabled])

  return state
}
