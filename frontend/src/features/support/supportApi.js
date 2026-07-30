const JSON_HEADERS = { Accept: 'application/json', 'Content-Type': 'application/json' }

function authHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { ...JSON_HEADERS, ...authHeaders(), ...(options.headers || {}) },
  })
  const text = await response.text()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!response.ok) throw new Error(payload?.detail || `Actie mislukt (HTTP ${response.status})`)
  return payload
}

export function listHouseholdThreads(status = '') {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request(`/api/support/threads${query}`)
}

export function readHouseholdThread(threadId) {
  return request(`/api/support/threads/${encodeURIComponent(threadId)}`)
}

export function createHouseholdThread(payload) {
  return request('/api/support/threads', { method: 'POST', body: JSON.stringify(payload) })
}

export function replyHouseholdThread(threadId, message) {
  return request(`/api/support/threads/${encodeURIComponent(threadId)}/messages`, {
    method: 'POST', body: JSON.stringify({ message }),
  })
}

export function listPlatformThreads({ status = '', householdId = '' } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (householdId) params.set('household_id', householdId)
  const query = params.toString() ? `?${params}` : ''
  return request(`/api/platform/support/threads${query}`)
}

export function readPlatformThread(threadId) {
  return request(`/api/platform/support/threads/${encodeURIComponent(threadId)}`)
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
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return fetch(`/api/platform/support/export.csv${query}`, { headers: authHeaders() }).then(async (response) => {
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
