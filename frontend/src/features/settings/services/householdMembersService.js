import { fetchJsonWithAuth } from '../../../lib/authSession'

async function parseJson(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data?.detail || 'Verzoek mislukt.')
    error.status = response.status
    throw error
  }
  return data
}

export async function fetchHouseholdMembers() {
  const response = await fetchJsonWithAuth('/api/household/members', {
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}

export async function createHouseholdMember(payload) {
  const response = await fetchJsonWithAuth('/api/household/members', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateHouseholdName(payload) {
  const response = await fetchJsonWithAuth('/api/household/name', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateHouseholdPermissionPolicy(permissionKey, payload) {
  const response = await fetchJsonWithAuth(`/api/household/permissions/${encodeURIComponent(permissionKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateHouseholdMember(email, payload) {
  const response = await fetchJsonWithAuth(`/api/household/members/${encodeURIComponent(email)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteHouseholdMember(email) {
  const response = await fetchJsonWithAuth(`/api/household/members/${encodeURIComponent(email)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}

export async function fetchHouseholdRoleAudit() {
  const response = await fetchJsonWithAuth('/api/household/role-audit', {
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}
