import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function fetchAvailability() {
  const response = await fetchJsonWithAuth('/api/action-buttons')
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Acties op de Startpagina konden niet worden geladen.')

  const rows = (payload.items || []).filter((item) => item?.home_tile_key)
  const items = Object.fromEntries(
    rows.map((item) => [String(item.home_tile_key), Boolean(item.enabled)]),
  )
  const order = [...rows]
    .sort((a, b) => Number(a?.sort_order ?? 9999) - Number(b?.sort_order ?? 9999))
    .map((item) => String(item.home_tile_key))

  return { items, order }
}

export function refreshActionButtonAvailability() {
  window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
}

export function useActionButtonAvailability({ enabled = true } = {}) {
  const [state, setState] = useState(() => ({
    items: {},
    order: [],
    ready: !enabled,
  }))

  useEffect(() => {
    let active = true

    if (!enabled) {
      setState({ items: {}, order: [], ready: true })
      return () => { active = false }
    }

    async function refresh() {
      setState((current) => ({
        items: current.ready ? current.items : {},
        order: current.ready ? current.order : [],
        ready: false,
      }))
      try {
        const projection = await fetchAvailability()
        if (active) setState({ ...projection, ready: true })
      } catch {
        if (active) setState({ items: {}, order: [], ready: true })
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
