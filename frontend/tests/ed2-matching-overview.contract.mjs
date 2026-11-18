import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { readMatchingOverview } from '../src/features/externalDatabases/ed2MatchingOverview.js'

const rows = [
  { id: 'receipt-table-line:one', receipt_line_text: 'MELK', retailer_code: 'ah',
    identity_status: 'not_identified', automatic_match_review_reason: 'Twee uitvoeringen' },
  { id: 'receipt-table-line:two', receipt_line_text: 'MELK', retailer_code: 'jumbo',
    identity_status: 'catalog_linked', catalog_product_id: 'proved-product',
    receipt_article_number: '123' },
]
const response = { ok: true, barcode_written: false, linked: 0, limit_reached: false,
  matching_overview: { items: rows, total: 2 } }
assert.deepEqual(readMatchingOverview(response), rows)
assert.deepEqual(readMatchingOverview({ ...response,
  matching_overview: { items: [], total: 0 } }), [])
for (const invalid of [
  { ...response, linked: 1 },
  { ...response, limit_reached: true },
  { ...response, barcode_written: true },
  { ...response, ok: false },
  { ...response, matching_overview: null },
  { ...response, matching_overview: { items: rows, total: 1 } },
  { ...response, matching_overview: { items: [...rows, rows[0]], total: 3 } },
  { ...response, matching_overview: { items: [{ ...rows[0], id: '' }], total: 1 } },
  { ...response, matching_overview: { items: [{ ...rows[0], identity_status: 'unknown' }], total: 1 } },
]) assert.equal(readMatchingOverview(invalid), null, 'Must fall back to authenticated GET')
const workspace = readFileSync(
  new URL('../src/features/externalDatabases/Ed2MatchPage.jsx', import.meta.url), 'utf8')
assert.match(workspace, /stableOverview = readMatchingOverview\(summary\)/)
assert.match(workspace, /const loaded = stableOverview\.map\(displayRow\)/)
assert.match(workspace, /await reload\(\)/)
assert.match(workspace, /if \(!batchLinked && !summary\.limit_reached\)/)
assert.match(workspace, /<DataTable columns=\{columns\} data=\{rows\}/)
console.log('ED2_MATCHING_SNAPSHOT_CONTRACT_GREEN')
