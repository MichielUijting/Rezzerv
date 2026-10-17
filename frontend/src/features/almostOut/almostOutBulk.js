import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession.js'

function csvCell(value) {
  return '"' + String(value ?? '').replaceAll('"', '""') + '"'
}

export function exportAlmostOutRows(rows) {
  if (!rows.length) return
  const columns = ['Huishoudartikel', 'Product', 'Huidig', 'Minimum', 'Te kopen', 'Locatie']
  const values = rows.map((row) => [
    row.householdName || row.primaryName || '',
    row.productName || '',
    row.currentQuantity ?? 0,
    row.minStock ?? 0,
    row.amountToBuy ?? 0,
    row.location || '',
  ])
  const csv = '\uFEFF' + [columns, ...values].map((line) => line.map(csvCell).join(';')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'inhuis-bijna-op-selectie.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function almostOutRequest(path, options = {}) {
  const response = await fetchJsonWithAuth(path, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'De verwerking van Bijna op is mislukt')
  return payload
}

export async function moveAlmostOutToShopping(rows) {
  let transferred = 0
  for (const row of rows) {
    if (!row.id) throw new Error('Artikelidentiteit ontbreekt')
    await almostOutRequest('/api/shopping-list/items', {
      method: 'POST',
      body: JSON.stringify({
        article_name: row.householdName || row.primaryName || row.productName,
        article_group_name: '',
        product_type_name: row.productName || '',
        source_type: 'household_article',
        source_id: row.id,
      }),
    })
    // Only hide a Bijna op row AFTER Shopping has accepted this article.
    // Persist the state so it stays hidden after refresh/navigation.
    const id = await householdId()
    await almostOutRequest('/api/households/' + id + '/almost-out/mark-in-shopping', {
      method: 'POST',
      body: JSON.stringify({ article_ids: [row.id] }),
    })
    transferred += 1
  }
  return transferred
}

async function householdId() {
  const storedId = String(readStoredAuthContext()?.active_household_id || '').trim()
  if (storedId) return encodeURIComponent(storedId)
  const response = await almostOutRequest('/api/household', { method: 'GET' })
  const resolvedId = String(response?.active_household_id || response?.id || '').trim()
  if (!resolvedId) throw new Error('Het actieve huishouden ontbreekt')
  return encodeURIComponent(resolvedId)
}

export async function hideAlmostOutRows(rows) {
  const id = await householdId()
  return almostOutRequest('/api/households/' + id + '/almost-out/hide', {
    method: 'POST',
    body: JSON.stringify({ article_ids: rows.map((row) => row.id) }),
  })
}

export async function restoreAlmostOutRows() {
  const id = await householdId()
  return almostOutRequest('/api/households/' + id + '/almost-out/restore', {
    method: 'POST',
  })
}
