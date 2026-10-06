import { fetchJsonWithAuth } from '../../lib/authSession.js'

export async function fetchHouseholdDashboard() {
  const response = await fetchJsonWithAuth('/api/dashboard', {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Pragma: 'no-cache',
    },
  })
  const text = await response.text()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!response.ok) throw new Error(payload?.detail || 'Dashboard kon niet worden geladen.')
  return payload
}


export async function fetchHouseholdDashboardDrilldown({
  metric,
  granularity,
  bucketIndex,
  series = 'current',
  comparison = 'previous',
  groupKey = '',
}) {
  const params = new URLSearchParams({
    metric,
    granularity,
    bucket_index: String(bucketIndex),
    series,
    comparison,
  })
  if (groupKey) params.set('group_key', groupKey)
  const response = await fetchJsonWithAuth('/api/dashboard/drilldown?' + params.toString(), {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Pragma: 'no-cache',
    },
  })
  const text = await response.text()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!response.ok) throw new Error(payload?.detail || 'Dashboarddetail kon niet worden geladen.')
  return payload
}


export async function fetchAlmostOutCount(householdId) {
  const normalizedHouseholdId = String(householdId || '').trim()
  if (!normalizedHouseholdId) return null
  const response = await fetchJsonWithAuth(`/api/households/${encodeURIComponent(normalizedHouseholdId)}/almost-out`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Bijna-op-aantal kon niet worden geladen.')
  return Array.isArray(payload?.items) ? payload.items.length : 0
}

export async function fetchRetailerPendingReceiptSummary() {
  const response = await fetchJsonWithAuth('/api/receipts/retailers/pending-summary', {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Downloadbare bonnen konden niet worden geteld.')
  return payload
}
