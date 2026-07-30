import { fetchJsonWithAuth, readStoredAuthContext } from '../../../lib/authSession'

function activeHouseholdId() {
  const context = readStoredAuthContext()
  const householdId = String(context?.active_household_id || '').trim()
  if (!householdId) {
    throw new Error('Geen actief huishouden beschikbaar. Log opnieuw in of selecteer een huishouden.')
  }
  return householdId
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : detail?.reason || 'Verzoek mislukt.'
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return data
}

function endpoint(path = '') {
  return `/api/households/${encodeURIComponent(activeHouseholdId())}/authorization${path}`
}

export async function fetchAuthorizationOverview() {
  const householdId = activeHouseholdId()
  const responses = await Promise.all([
    fetchJsonWithAuth(`/api/households/${encodeURIComponent(householdId)}/authorization/members`, { headers: { Accept: 'application/json' } }),
    fetchJsonWithAuth(`/api/households/${encodeURIComponent(householdId)}/authorization/roles`, { headers: { Accept: 'application/json' } }),
    fetchJsonWithAuth(`/api/households/${encodeURIComponent(householdId)}/authorization/permissions`, { headers: { Accept: 'application/json' } }),
  ])
  const [members, roles, permissions] = await Promise.all(responses.map(parseJson))
  return {
    householdId: String(members?.household_id || householdId),
    members: Array.isArray(members?.items) ? members.items : [],
    roles: Array.isArray(roles?.items) ? roles.items : [],
    permissions: Array.isArray(permissions?.items) ? permissions.items : [],
  }
}

export async function updateAuthorizationRole(membershipId, roleKey) {
  const response = await fetchJsonWithAuth(endpoint(`/members/${encodeURIComponent(membershipId)}/role`), {
    method: 'PUT',
    body: JSON.stringify({ role_key: roleKey }),
  })
  return parseJson(response)
}

export async function setAuthorizationPermission(membershipId, permissionKey, effect) {
  const response = await fetchJsonWithAuth(endpoint(`/members/${encodeURIComponent(membershipId)}/permissions/${encodeURIComponent(permissionKey)}`), {
    method: 'PUT',
    body: JSON.stringify({ effect }),
  })
  return parseJson(response)
}

export async function deleteAuthorizationPermission(membershipId, permissionKey) {
  const response = await fetchJsonWithAuth(endpoint(`/members/${encodeURIComponent(membershipId)}/permissions/${encodeURIComponent(permissionKey)}`), {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}
