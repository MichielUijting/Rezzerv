const JSON_HEADERS = { Accept: 'application/json', 'Content-Type': 'application/json' }

function authHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function activeHouseholdHeaders() {
  try {
    const raw = localStorage.getItem('rezzerv_auth_context')
    const context = raw ? JSON.parse(raw) : null
    const householdId = String(context?.active_household_id || '').trim()
    return householdId ? { 'X-Rezzerv-Household-ID': householdId } : {}
  } catch {
    return {}
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers: {
      ...JSON_HEADERS,
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Pragma: 'no-cache',
      ...authHeaders(),
      ...activeHouseholdHeaders(),
      ...(options.headers || {}),
    },
  })
  const text = await response.text()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!response.ok) throw new Error(payload?.detail || `Actie mislukt (HTTP ${response.status})`)
  return payload
}

function freshQuery(params = new URLSearchParams()) {
  params.set('_refresh', String(Date.now()))
  return `?${params.toString()}`
}

export function listHouseholdThreads(status = '') {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  return request(`/api/support/threads${freshQuery(params)}`)
}

export function readHouseholdThread(threadId) {
  return request(`/api/support/threads/${encodeURIComponent(threadId)}${freshQuery()}`)
}

export function createHouseholdThread(payload) {
  return request('/api/support/threads', { method: 'POST', body: JSON.stringify(payload) })
}

export function replyHouseholdThread(threadId, message) {
  return request(`/api/support/threads/${encodeURIComponent(threadId)}/messages`, {
    method: 'POST', body: JSON.stringify({ message }),
  })
}

export function updateHouseholdThreadStatus(threadId, status) {
  return request(`/api/support/threads/${encodeURIComponent(threadId)}/status`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  })
}

export function listPlatformThreads({ status = '', householdId = '' } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (householdId) params.set('household_id', householdId)
  return request(`/api/platform/support/threads${freshQuery(params)}`)
}

export function readPlatformThread(threadId) {
  return request(`/api/platform/support/threads/${encodeURIComponent(threadId)}${freshQuery()}`)
}

export function createPlatformThread(payload) {
  return request('/api/platform/support/threads', { method: 'POST', body: JSON.stringify(payload) })
}

export function replyPlatformThread(threadId, message) {
  return request(`/api/platform/support/threads/${encodeURIComponent(threadId)}/messages`, {
    method: 'POST', body: JSON.stringify({ message }),
  })
}

export function updatePlatformThreadStatus(threadId, status) {
  return request(`/api/platform/support/threads/${encodeURIComponent(threadId)}/status`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  })
}

export function downloadPlatformSupportCsv(status = '') {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  const query = freshQuery(params)
  return fetch(`/api/platform/support/export.csv${query}`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', ...authHeaders() },
  }).then(async (response) => {
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'CSV-export mislukt')
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = 'rezzerv-meldingen.csv'
    anchor.click()
    URL.revokeObjectURL(href)
  })
}
