import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth, getAuthHeaders } from '../../../lib/authSession'

export const RECEIPT_SCANNER_OPTIONS = [
  { value: 'inhuis', label: 'Inhuis-scanner', description: 'De huidige ingebouwde kassabonscanner van Inhuis.' },
  { value: 'in-huis-demo', label: 'AI', description: 'Gebruikt AI-bonherkenning op de achtergrond. Je blijft volledig in Inhuis; Kassa en Uitpakken blijven ongewijzigd.' },
]

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

export async function saveStoreImportSimplificationSettings(store_import_simplification_level, receipt_scanner_provider) {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/store-import-settings`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ store_import_simplification_level, receipt_scanner_provider }),
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

export async function saveReceiptScannerProvider(receipt_scanner_provider) {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/receipt-scanner-provider`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ receipt_scanner_provider }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Kassabonscanner kon niet worden opgeslagen.')
  return data
}
