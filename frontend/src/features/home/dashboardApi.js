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
}) {
  const params = new URLSearchParams({
    metric,
    granularity,
    bucket_index: String(bucketIndex),
    series,
    comparison,
  })
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
