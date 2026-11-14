// Pure read-only projection: no name or retailer text is ever an identity key.
// Only canonical backend-confirmed Catalogus IDs establish a Match. Only
// server-confirmed direct article-synonym pairs establish Synoniem edges.
const nameKey = (value) => String(value || '').normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ')

const receiptSort = (a, b) =>
  String(a.retailer_code || '').localeCompare(String(b.retailer_code || ''), 'nl')
  || String(a.receipt_line_text || '').localeCompare(String(b.receipt_line_text || ''), 'nl')
  || String(a.receipt_article_number || '').localeCompare(String(b.receipt_article_number || ''), 'nl')

export function buildArticleRelationshipGraph(catalogItems, receiptItems, synonymOptions, selectedId) {
  const products = new Map((catalogItems || []).map((product) => [String(product.id), product]))
  const root = products.get(String(selectedId || ''))
  if (!root) return null

  const peers = (synonymOptions || [])
    .filter((option) => option.status === 'linked' && String(option.id) !== String(root.id))
    .map((option) => products.get(String(option.id)))
    .filter(Boolean)
    .filter((product, index, all) => all.findIndex((entry) => entry.id === product.id) === index)
    .sort((a, b) => String(a.name).localeCompare(String(b.name), 'nl'))
  const ids = [String(root.id), ...peers.map((product) => String(product.id))]
  const known = new Set(ids)
  const matched = new Map(ids.map((id) => [id, []]))
  const pending = []
  for (const row of receiptItems || []) {
    // The ED2 projection distinguishes identification from classification.
    // A GS1-pending receipt can still have a confirmed Catalogus identity.
    if (row.identity_status !== 'catalog_linked') continue
    const canonical = String(row.identity_catalog_product_id || '')
    const legacy = String(row.catalog_product_id || '')
    if (canonical && legacy && canonical !== legacy) continue // Conflicting proof.
    const productId = canonical || legacy
    if (known.has(productId)) matched.get(productId).push(row)
  }
  for (const rows of matched.values()) rows.sort(receiptSort)
  // An exact name overlap is only an unconfirmed *review candidate*. It must
  // NEVER be drawn as a Match/Synoniem or used as a product identity.
  const confirmedNames = new Set([...matched.values()].flat().map(
    (row) => nameKey(row.receipt_line_text)).filter(Boolean))
  for (const row of receiptItems || []) {
    if (row.identity_status !== 'not_identified' && row.identity_status !== 'review') continue
    if (confirmedNames.has(nameKey(row.receipt_line_text))) pending.push(row)
  }
  pending.sort(receiptSort)
  const synonymCards = peers.map((product) => ({
    product, receipts: matched.get(String(product.id)) || [],
  }))
  return {
    root, rootReceipts: matched.get(String(root.id)) || [],
    synonyms: synonymCards, pending,
    counts: {
      matches: (matched.get(String(root.id)) || []).length,
      variantMatches: synonymCards.reduce((sum, item) => sum + item.receipts.length, 0),
      synonyms: peers.length, pending: pending.length,
    },
  }
}