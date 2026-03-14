import { API_BASE_URL } from '../../../lib/apiClient'

const STORAGE_KEY = 'rezzerv_household_auto_consume_on_repurchase'
const EVENT_NAME = 'rezzerv-household-automation-updated'

function getAuthHeaders() {
  const token = window.localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function normalizeSettings(value) {
  return {
    autoConsumeOnRepurchase: Boolean(value?.autoConsumeOnRepurchase ?? value?.auto_consume_on_repurchase),
    hasExplicitValue: Boolean(value?.hasExplicitValue ?? value?.has_explicit_value),
  }
}

function saveLocal(settings) {
  const normalized = normalizeSettings(settings)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}

export function getHouseholdAutomationSettings() {
  try {
    return normalizeSettings(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}'))
  } catch {
    return normalizeSettings({})
  }
}

function readLegacyLocalValue() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}')
    if (Object.prototype.hasOwnProperty.call(parsed || {}, 'autoConsumeOnRepurchase')) {
      return Boolean(parsed.autoConsumeOnRepurchase)
    }
    if (Object.prototype.hasOwnProperty.call(parsed || {}, 'auto_consume_on_repurchase')) {
      return Boolean(parsed.auto_consume_on_repurchase)
    }
  } catch {
    // ignore legacy parse errors
  }
  return null
}

export async function fetchHouseholdAutomationSettings() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/household/automation-settings`, {
      method: 'GET',
      headers: { Accept: 'application/json', ...getAuthHeaders() },
      credentials: 'include',
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data?.detail || 'Instellingen konden niet worden geladen.')
    }
    const normalized = normalizeSettings(data)
    if (!normalized.hasExplicitValue) {
      const legacyValue = readLegacyLocalValue()
      if (legacyValue !== null) {
        return saveHouseholdAutomationSettings({ autoConsumeOnRepurchase: legacyValue })
      }
    }
    return saveLocal(normalized)
  } catch {
    return getHouseholdAutomationSettings()
  }
}

export async function saveHouseholdAutomationSettings(settings = {}) {
  const normalized = normalizeSettings(settings)
  const response = await fetch(`${API_BASE_URL}/api/household/automation-settings`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...getAuthHeaders(),
    },
    credentials: 'include',
    body: JSON.stringify({ auto_consume_on_repurchase: normalized.autoConsumeOnRepurchase }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Opslaan is niet gelukt.')
  }
  const saved = saveLocal({ ...data, has_explicit_value: true })
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: saved }))
  return saved
}
