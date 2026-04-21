import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth, getAuthHeaders } from '../../../lib/authSession'

export const STORE_IMPORT_SIMPLIFICATION_LEVELS = [
  { value: 'voorzichtig', label: 'Voorzichtig', description: 'Alleen voorstellen, jij controleert alles.' },
  { value: 'gebalanceerd', label: 'Gebalanceerd', description: 'Bekende keuzes worden voorbereid, twijfel blijft open.' },
  { value: 'maximaal_gemak', label: 'Maximaal gemak', description: 'Bekende regels worden zo veel mogelijk automatisch klaargezet.' },
]

const EVENT_NAME = 'rezzerv-store-import-simplification-updated'

export function getStoreImportSimplificationLabel(value) {
  return STORE_IMPORT_SIMPLIFICATION_LEVELS.find((option) => option.value === value)?.label || 'Gebalanceerd'
}

export async function getStoreImportSimplificationSettings() {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/store-import-settings`, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Instellingen konden niet worden geladen.')
  }
  return data
}

export async function saveStoreImportSimplificationSettings(store_import_simplification_level) {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/store-import-settings`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ store_import_simplification_level }),
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Instellingen konden niet worden opgeslagen.')
  }

  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: data }))
  return data
}

export function subscribeToStoreImportSimplificationUpdates(listener) {
  window.addEventListener(EVENT_NAME, listener)
  return () => window.removeEventListener(EVENT_NAME, listener)
}
