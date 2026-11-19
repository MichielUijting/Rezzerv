/**
 * A completed, authorized zero-write matching POST already contains the
 * fully resolved receipt identity snapshot used by the server's proof scan.
 * Reject partial/inconsistent responses and fall back to the canonical GET.
 */
export function readMatchingOverview(summary) {
  if (summary?.ok !== true || summary?.barcode_written !== false
      || summary?.linked !== 0 || summary?.limit_reached !== false) return null
  const overview = summary.matching_overview
  if (!overview || !Array.isArray(overview.items)
      || !Number.isSafeInteger(overview.total) || overview.total !== overview.items.length) return null
  const seen = new Set()
  for (const row of overview.items) {
    if (!row || typeof row.id !== 'string' || !row.id || seen.has(row.id)
        || typeof row.receipt_line_text !== 'string'
        || typeof row.retailer_code !== 'string'
        || !['not_identified', 'saved_only', 'catalog_linked', 'review'].includes(row.identity_status)) {
      return null
    }
    seen.add(row.id)
  }
  return overview.items
}
