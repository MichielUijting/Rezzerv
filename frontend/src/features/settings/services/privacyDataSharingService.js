import { fetchJsonWithAuth } from '../../../lib/authSession'

export async function fetchPrivacyDataSharingSettings() {
  const response = await fetchJsonWithAuth('/api/settings/privacy-data-sharing')
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Privacy-instellingen konden niet worden geladen.')
  return data
}

export async function updatePrivacyDataSharingSettings(payload) {
  const response = await fetchJsonWithAuth('/api/settings/privacy-data-sharing', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Privacy-instellingen konden niet worden opgeslagen.')
  return data
}
