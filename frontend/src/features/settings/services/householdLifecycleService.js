import { fetchJsonWithAuth } from '../../../lib/authSession'

async function parseJson(response, fallbackMessage) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : ''
    throw new Error(detail || fallbackMessage)
  }
  return payload
}

export async function fetchMyHouseholds() {
  const response = await fetchJsonWithAuth('/api/session/households', {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  return parseJson(response, 'Huishoudens konden niet worden geladen.')
}

export async function createAdditionalHousehold(householdName) {
  const response = await fetchJsonWithAuth('/api/session/households', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ household_name: String(householdName || '').trim() }),
  })
  return parseJson(response, 'Nieuw huishouden kon niet worden gemaakt.')
}

export async function deleteAdditionalHousehold(householdId, confirmation) {
  const response = await fetchJsonWithAuth(
    `/api/session/households/${encodeURIComponent(householdId)}`,
    {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ confirmation }),
    },
  )
  return parseJson(response, 'Huishouden kon niet worden verwijderd.')
}
