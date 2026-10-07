import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function fetchAvailability() {
  const [response, actionBarResponse] = await Promise.all([
    fetchJsonWithAuth('/api/action-buttons'),
    fetchJsonWithAuth('/api/platform/mobile-action-bar'),
  ])
  const payload = await response.json().catch(() => ({}))
  const actionBarPayload = await actionBarResponse.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Acties op de Startpagina konden niet worden geladen.')
  if (!actionBarResponse.ok) throw new Error(actionBarPayload?.detail || 'Actiebalkinstelling kon niet worden geladen.')

  const rows = (payload.items || []).filter((item) => item?.home_tile_key)
  const items = Object.fromEntries(
    rows.map((item) => [String(item.home_tile_key), Boolean(item.enabled)]),
  )
  const order = [...rows]
    .sort((a, b) => Number(a?.sort_order ?? 9999) - Number(b?.sort_order ?? 9999))
    .map((item) => String(item.home_tile_key))

  return {
    items,
    order,
    welcomeText: String(payload?.welcome_text || 'Fijn dat je er weer bent.').trim(),
    actionBarLocked: Boolean(actionBarPayload?.locked),
    fixedActionBarKeys: Array.isArray(actionBarPayload?.fixed_keys) ? actionBarPayload.fixed_keys.map(String) : [],
  }
}

export function refreshActionButtonAvailability() {
  window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
}

export function useActionButtonAvailability({ enabled = true } = {}) {
  const [state, setState] = useState(() => ({
    items: {},
    order: [],
    welcomeText: 'Fijn dat je er weer bent.',
    actionBarLocked: true,
    fixedActionBarKeys: ['winkelen', 'kassa', 'kassabonnen', 'voorraad'],
    ready: !enabled,
  }))

  useEffect(() => {
    let active = true

    if (!enabled) {
      setState({
        items: {},
        order: [],
        welcomeText: 'Fijn dat je er weer bent.',
        actionBarLocked: true,
        fixedActionBarKeys: ['winkelen', 'kassa', 'kassabonnen', 'voorraad'],
        ready: true,
      })
      return () => { active = false }
    }

    async function refresh() {
      setState((current) => current.ready
        ? current
        : {
          items: {},
          order: [],
          welcomeText: 'Fijn dat je er weer bent.',
          actionBarLocked: true,
          fixedActionBarKeys: ['winkelen', 'kassa', 'kassabonnen', 'voorraad'],
          ready: false,
        })
      try {
        const projection = await fetchAvailability()
        if (active) setState({ ...projection, ready: true })
      } catch {
        if (active) setState({
          items: {},
          order: [],
          welcomeText: 'Fijn dat je er weer bent.',
          actionBarLocked: true,
          fixedActionBarKeys: ['winkelen', 'kassa', 'kassabonnen', 'voorraad'],
          ready: true,
        })
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
