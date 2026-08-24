import { fetchJsonWithAuth } from '../../../lib/authSession'

function resolveErrorMessage(data) {
  const detail = data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const deliveryMessage = detail?.delivery?.message
    if (typeof deliveryMessage === 'string' && deliveryMessage.trim()) return deliveryMessage
    if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message
  }
  if (typeof data?.message === 'string' && data.message.trim()) return data.message
  return 'Verzoek mislukt.'
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(resolveErrorMessage(data))
    error.status = response.status
    error.payload = data
    throw error
  }
  return data
}

export async function fetchHouseholdInvitations() {
  const response = await fetchJsonWithAuth('/api/household/invitations', {
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}

export async function createHouseholdInvitation(payload) {
  const response = await fetchJsonWithAuth('/api/household/invitations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ email: payload?.email }),
  })
  return parseJson(response)
}

export async function resendHouseholdInvitation(invitationId) {
  const response = await fetchJsonWithAuth(`/api/household/invitations/${encodeURIComponent(invitationId)}/resend`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}

export async function revokeHouseholdInvitation(invitationId) {
  const response = await fetchJsonWithAuth(`/api/household/invitations/${encodeURIComponent(invitationId)}/revoke`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  return parseJson(response)
}
