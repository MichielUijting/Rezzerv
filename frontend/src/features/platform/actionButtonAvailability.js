import { useEffect, useMemo, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const ACTION_KEYS_BY_TEST_ID = Object.freeze({
  'kassa-add-receipt-button': 'action.kassa.add_receipt',
  'kassa-choose-file-button': 'action.kassa.choose_files',
  'kassa-open-camera-button': 'action.kassa.open_camera',
  'kassa-camera-confirm': 'action.kassa.camera_confirm',
  'kassa-delete-selected-button': 'action.kassa.delete_selected',
  'receipt-lines-mark-reviewed': 'action.kassa.lines_mark_reviewed',
  'receipt-export-button': 'action.kassa.lines_export',
  'inventory-add-incidental-purchase': 'action.inventory.add_incidental_purchase',
  'inventory-incidental-open-barcode-camera': 'action.inventory.scan_barcode',
})

const ACTION_KEYS_BY_TEXT = Object.freeze({
  Goedkeuren: 'action.kassa.approve_receipt',
  'Winkelen afgerond': 'action.shopping.complete',
})

let availability = null
let loadPromise = null
const listeners = new Set()

function publish(nextAvailability) {
  availability = nextAvailability
  for (const listener of listeners) listener(availability)
}

function resolveActionKey({ actionKey, testId, label }) {
  if (actionKey) return String(actionKey)
  if (testId && ACTION_KEYS_BY_TEST_ID[testId]) return ACTION_KEYS_BY_TEST_ID[testId]
  if (label && ACTION_KEYS_BY_TEXT[label]) return ACTION_KEYS_BY_TEXT[label]
  return null
}

async function loadAvailability({ force = false } = {}) {
  if (!force && availability) return availability
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    try {
      const response = await fetchJsonWithAuth('/api/action-buttons')
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Actieknoppen konden niet worden geladen.')
      const next = Object.fromEntries((payload.items || []).map((item) => [String(item.key), Boolean(item.enabled)]))
      publish(next)
      return next
    } catch {
      // Availability is additive to authorization and must not break existing UI when
      // the projection is temporarily unavailable. Registered buttons default to ON.
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

export function useActionButtonEnabled({ actionKey = null, testId = null, label = '' } = {}) {
  const resolvedKey = useMemo(
    () => resolveActionKey({ actionKey, testId, label }),
    [actionKey, testId, label],
  )
  const [snapshot, setSnapshot] = useState(availability)

  useEffect(() => {
    if (!resolvedKey) return undefined
    const listener = (next) => setSnapshot(next)
    listeners.add(listener)
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
  }, [resolvedKey])

  if (!resolvedKey) return true
  if (!snapshot || snapshot[resolvedKey] == null) return true
  return snapshot[resolvedKey] !== false
}
