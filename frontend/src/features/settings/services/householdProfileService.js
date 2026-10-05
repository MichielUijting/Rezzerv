import { fetchJsonWithAuth } from '../../../lib/authSession.js'

async function request(path, options = {}) {
  const response = await fetchJsonWithAuth(path, {
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Huishoudprofiel kon niet worden bijgewerkt.')
  return payload
}

export function fetchHouseholdProfile() {
  return request('/api/household/profile')
}

export function saveHouseholdProfile(payload) {
  return request('/api/household/profile', { method: 'PUT', body: JSON.stringify(payload) })
}

export function createHouseholdResident(payload) {
  return request('/api/household/profile/residents', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateHouseholdResident(residentId, payload) {
  return request(`/api/household/profile/residents/${encodeURIComponent(residentId)}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteHouseholdResident(residentId) {
  return request(`/api/household/profile/residents/${encodeURIComponent(residentId)}`, { method: 'DELETE' })
}
