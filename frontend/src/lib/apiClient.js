const API_BASE = 'http://localhost:8000'

export async function apiPost(path, body) {
  const token = localStorage.getItem('rezzerv_token') || ''
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  return res
}

export const API_BASE_URL = API_BASE
