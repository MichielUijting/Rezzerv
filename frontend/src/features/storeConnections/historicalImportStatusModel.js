// A persisted queue item is not proof of a receipt stored in Kassa.
// The retailer may not disclose a total number of historical receipts.
export function historyCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString('nl-NL') : '—'
}

export function hasPendingHistoryWork(summary) {
  if (!summary || summary.auto_import_paused === true) return false
  const rows = Array.isArray(summary.providers) ? summary.providers : []
  return rows.some(row => Number(row?.queue_pending) > 0 || Number(row?.queue_processing) > 0)
}

export function historicalStoreRows(summary) {
  if (!summary || !Array.isArray(summary.providers)) return []
  const names = { ah: 'Albert Heijn', lidl: 'Lidl', jumbo: 'Jumbo' }
  return ['ah', 'lidl', 'jumbo'].map(code => {
    const row = summary.providers.find(item => item?.code === code) || {}
    return { ...row, code, name: names[code] }
  })
}
