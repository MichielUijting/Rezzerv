import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth, getAuthHeaders } from '../../../lib/authSession'

export async function getExternalDatabasesConfig() {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/external-databases/config`, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Configuratie voor externe databases kon niet worden geladen.')
  }
  return data
}

export async function previewRetailerExternalDatabaseMatch(retailerCode, receiptLineText, includeBelowThreshold = true) {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/external-databases/retailers/${encodeURIComponent(retailerCode)}/match-preview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ receipt_line_text: receiptLineText, include_below_threshold: includeBelowThreshold }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Match-preview kon niet worden uitgevoerd.')
  }
  return data
}
