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
    transferred += 1
  }
  return transferred
}

function householdId() {
  const id = String(readStoredAuthContext()?.active_household_id || '').trim()
  if (!id) throw new Error('Het actieve huishouden ontbreekt')
  return encodeURIComponent(id)
}

export function hideAlmostOutRows(rows) {
  return almostOutRequest('/api/households/' + householdId() + '/almost-out/hide', {
    method: 'POST',
    body: JSON.stringify({ article_ids: rows.map((row) => row.id) }),
  })
}

export function restoreAlmostOutRows() {
  return almostOutRequest('/api/households/' + householdId() + '/almost-out/restore', {
    method: 'POST',
  })
}
