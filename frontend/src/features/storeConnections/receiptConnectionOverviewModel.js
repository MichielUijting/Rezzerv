// Digital receipt availability is not the same thing as a loyalty card connection.
// Never infer a retailer login, installed browser bookmarklet, or background sync
// from an existing customer-card reference.
const DIGITAL_STORES = [
  { code: 'ah', name: 'Albert Heijn' },
  { code: 'jumbo', name: 'Jumbo' },
  { code: 'lidl', name: 'Lidl' },
  { code: 'picnic', name: 'Picnic' },
  { code: 'aldi', name: 'Aldi' },
  { code: 'plus', name: 'PLUS' },
]

// A first import has no confirmed checkpoint. Show a real starting point,
// not a fake synchronization timestamp, and share it with the date inputs.
export function firstImportDate(now = new Date()) {
  return `${now.getFullYear() - 1}-01-01`
}

export function safeImportDate(value, now = new Date()) {
  if (typeof value !== 'string' || !/^\\d{4}-\\d{2}-\\d{2}$/.test(value)) return null
  const parsed = new Date(value + 'T00:00:00Z')
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) return null
  const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-')
  return value <= today ? value : null
}

export function displayedImportDate(value, now = new Date()) {
  const day = safeImportDate(value, now) || firstImportDate(now)
  const [year, month, date] = day.split('-')
  return { day, label: `${date}-${month}-${year}`, isDefault: !safeImportDate(value, now) }
}

export function deriveReceiptConnectionOverview(existingRows, ahConnection, importDates = {}, now = new Date()) {
  const known = new Map((Array.isArray(existingRows) ? existingRows : [])
    .map(row => [String(row.providerCode || '').toLowerCase(), row]))
  return DIGITAL_STORES.map(store => {
    const legacy = known.get(store.code)
    const base = {
      providerCode: store.code,
      providerName: store.name,
      lastSyncLabel: '—',
      isAvailable: true,
      isAutomatic: false,
      statusCode: 'browser',
      actionLabel: 'Instellen',
      statusLabel: 'Browserstap nodig',
      typeLabel: 'Via browser',
    }
    if (store.code === 'ah') {
      const connected = ahConnection?.connected === true
      return {
        ...base,
        isAutomatic: connected,
        statusCode: connected ? 'connected' : 'not_connected',
        statusLabel: connected ? 'Gekoppeld' : 'Niet gekoppeld',
        typeLabel: connected ? 'Automatisch' : 'Direct koppelen',
        actionLabel: connected ? 'Bekijken' : 'Koppelen',
        lastSyncLabel: connected ? legacy?.lastSyncLabel || '—' : '—',
      }
    }
    if (store.code === 'jumbo' || store.code === 'lidl') {
      const latest = displayedImportDate(importDates?.[store.code], now)
      return {
        ...base,
        actionLabel: 'Bonnen ophalen',
        lastSyncLabel: latest.label,
        lastUpdatedDate: latest.day,
        isDefaultImportDate: latest.isDefault,
      }
    }
    if (store.code === 'aldi' || store.code === 'plus') {
      return {
        ...base,
        isAvailable: false,
        statusCode: 'unavailable',
        statusLabel: 'Geen koppeling mogelijk',
        actionLabel: 'Geen koppeling mogelijk',
      }
    }
    return {
      ...base,
      isAvailable: false,
      statusCode: 'unavailable',
      statusLabel: 'Nog niet beschikbaar',
      actionLabel: 'Uitleg',
    }
  })
}

export function receiptConnectionSummary(rows) {
  const items = Array.isArray(rows) ? rows : []
  return {
    automatic: items.filter(row => row.isAutomatic).length,
    browser: items.filter(row => row.statusCode === 'browser').length,
    unavailable: items.filter(row => row.statusCode === 'unavailable').length,
  }
}
