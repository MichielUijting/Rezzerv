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

export function deriveReceiptConnectionOverview(existingRows, ahConnection) {
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
        typeLabel: 'Automatisch bij Kassa',
        actionLabel: connected ? 'Bekijken' : 'Koppelen',
        lastSyncLabel: connected ? legacy?.lastSyncLabel || '—' : '—',
      }
    }
    if (store.code === 'jumbo' || store.code === 'lidl') {
      return { ...base, actionLabel: 'Bonnen ophalen' }
    }
    return {
      ...base,
      isAvailable: false,
      isAutomatic: false,
      statusCode: 'unavailable',
      statusLabel: 'Nog niet beschikbaar',
      typeLabel: 'Geen automatische bonimport',
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
