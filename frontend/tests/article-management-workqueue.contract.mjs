import assert from 'node:assert/strict'
import { projectArticleWorkQueue } from '../src/features/externalDatabases/articleManagementWorkQueueModel.js'

const source = [
  { id: 'a1', retailer_code: 'ah', receipt_line_text: 'AH HV MELK',
    receipt_article_number: '45', identity_status: 'not_identified',
    automatic_match_review_reason: 'Twee afzonderlijk bewezen melkuitvoeringen.' },
  { id: 'a2', retailer_code: 'jumbo', receipt_line_text: 'AH HV MELK',
    receipt_article_number: '45', identity_status: 'not_identified' },
  { id: 'a3', retailer_code: 'lidl', receipt_line_text: 'WASMIDDEL',
    receipt_article_number: '0035', identity_status: 'saved_only',
    identity_repairable: true, manual_barcode: '8712345678901' },
  { id: 'a4', retailer_code: 'ah', receipt_line_text: 'ELSTAR',
    receipt_article_number: '69', identity_status: 'review', manual_barcode: '8711111111111' },
  { id: 'a5', retailer_code: 'ah', receipt_line_text: 'COURGETTE',
    receipt_article_number: '70', identity_status: 'catalog_linked',
    catalog_product_id: 'catalog-1' },
  { id: 'a6', retailer_code: 'jumbo', receipt_line_text: 'MELK',
    receipt_article_number: '21', identity_status: 'not_identified',
    automatic_match_review_reason: 'Meerdere uitvoeringen', manual_barcode: '8711111111111' },
]
const products = [{ id: 'product-1', name: 'Melk', gtin: '8712345678901' }]
const tasks = [
  { key: 'product-1:gpc', global_product_id: 'product-1', system: 'gpc', status: 'open' },
  { key: 'product-1:cbs', global_product_id: 'product-1', system: 'cbs', status: 'open' },
]
const admin = projectArticleWorkQueue(source, products, tasks, { isSuperuser: true })
assert.deepEqual(admin.counts, {
  review: 1, matching: 1, repair: 1, identify: 2, synonyms: 0, classify: 2,
})
assert.equal(admin.tasks.length, 7)
assert.equal(admin.tasks.find((task) => task.key === 'receipt:a1').area, 'matching')
assert.equal(admin.tasks.find((task) => task.key === 'receipt:a3').area, 'identity')
assert.equal(admin.tasks.find((task) => task.key === 'receipt:a6').type, 'identify')
assert.equal(admin.tasks.filter((task) => task.productId === 'product-1').length, 2)
assert.equal(admin.tasks.filter((task) => task.sourceId === 'a5').length, 0)

const conflict = projectArticleWorkQueue([
  { id: 'conflicted', retailer_code: 'ah', receipt_line_text: 'ELSTAR',
    identity_status: 'catalog_linked', catalog_product_id: 'p1',
    identity_catalog_product_id: 'p2', manual_barcode: '8712345678901' },
  { id: 'bad-barcode', retailer_code: 'jumbo', receipt_line_text: 'MELK',
    identity_status: 'catalog_linked', catalog_product_id: 'p1',
    manual_barcode: '8712345678901', article_code: '8712345678902' },
], [], [])
assert.deepEqual(conflict.counts, {
  review: 2, matching: 0, repair: 0, identify: 0, synonyms: 0, classify: 0,
})
assert.throws(() => projectArticleWorkQueue([
  { id: 'unproven', retailer_code: 'ah', receipt_line_text: 'MELK',
    identity_status: 'catalog_linked' },
], [], []), /centrale productidentiteit/i)


const equivalentGtinClaims = projectArticleWorkQueue([
  { id: 'waldk', retailer_code: 'ah', receipt_line_text: 'WALDK HALF',
    receipt_article_number: '', identity_status: 'catalog_linked',
    manual_barcode: '08719587106174', article_code: '8719587106174',
    identity_catalog_product_id: 'milk-product', catalog_product_id: 'milk-product' },
  { id: 'waldk-other-receipt', retailer_code: 'ah', receipt_line_text: 'WALDK HALF',
    receipt_article_number: '45653', identity_status: 'catalog_linked',
    manual_barcode: '8719587106174', article_code: '08719587106174',
    identity_catalog_product_id: 'milk-product', catalog_product_id: 'milk-product' },
], [], [])
assert.equal(equivalentGtinClaims.counts.review, 0)
assert.equal(equivalentGtinClaims.tasks.length, 0,
  'Equivalent GTIN-13/14 claims must not generate an Identificatie controleren task')

const realIdentityReviews = projectArticleWorkQueue([
  { id: 'owner-mismatch', retailer_code: 'ah', receipt_line_text: 'WALDK HALF',
    identity_status: 'catalog_linked', manual_barcode: '08719587106174',
    article_code: '8719587106174', catalog_product_id: 'milk-product',
    identity_catalog_product_id: 'other-product' },
  { id: 'different-gtins', retailer_code: 'ah', receipt_line_text: 'RISOTTORIJST',
    identity_status: 'catalog_linked', manual_barcode: '8722800072026',
    article_code: '8712345678906', catalog_product_id: 'product-1' },
  { id: 'bad-check-digit', retailer_code: 'ah', receipt_line_text: 'WALDK HALF',
    identity_status: 'catalog_linked', manual_barcode: '08719587106175',
    article_code: '8719587106174', catalog_product_id: 'milk-product' },
  { id: 'server-review', retailer_code: 'ah', receipt_line_text: 'ZK KNOFLOOKP',
    identity_status: 'review', manual_barcode: '8712200080646' },
  { id: 'saved-unrepairable', retailer_code: 'ah', receipt_line_text: 'ANDER ARTIKEL',
    identity_status: 'saved_only', identity_repairable: false,
    manual_barcode: '8712200080646' },
], [], [])
assert.equal(realIdentityReviews.counts.review, 5)
assert.match(realIdentityReviews.tasks.find(t => t.sourceId === 'owner-mismatch').reason,
  /verschillende Catalogusproducten/)
assert.match(realIdentityReviews.tasks.find(t => t.sourceId === 'different-gtins').reason,
  /barcode en de Catalogusbarcode verschillen/)
assert.match(realIdentityReviews.tasks.find(t => t.sourceId === 'bad-check-digit').reason,
  /barcode en de Catalogusbarcode verschillen/)
assert.match(realIdentityReviews.tasks.find(t => t.sourceId === 'server-review').reason,
  /status Te beoordelen/)
assert.match(realIdentityReviews.tasks.find(t => t.sourceId === 'saved-unrepairable').reason,
  /automatisch herstel/)

const frontteam = projectArticleWorkQueue(source, products, tasks)
assert.equal(frontteam.counts.matching, 0)
assert.equal(frontteam.tasks.some((task) => task.area === 'matching'), false)
assert.equal(frontteam.tasks.filter((task) => task.type === 'classify').length, 2)
assert.equal(frontteam.tasks.find((task) => task.sourceId === 'a2').type, 'identify')
const cbsOnly = projectArticleWorkQueue(source, products, tasks, {
  canClassifyGpc: false, canClassifyCbs: true,
})
assert.equal(cbsOnly.counts.classify, 1)
assert.equal(cbsOnly.tasks.find((task) => task.type === 'classify').system, 'cbs')

for (const [receipts, classes, classification, expected] of [
  [[source[0], source[0]], products, tasks, /dubbel/i],
  [[{ ...source[0], id: '' }], products, tasks, /onvolledig/i],
  [[{ ...source[0], identity_status: 'unexpected' }], products, tasks, /onbekende/i],
  [source, [products[0], products[0]], tasks, /dubbel/i],
  [source, products, [tasks[0], tasks[0]], /dubbele/i],
  [source, products, [{ ...tasks[0], global_product_id: 'unknown' }], /onbekende/i],
]) {
  assert.throws(() => projectArticleWorkQueue(receipts, classes, classification), expected)
}

const withSynonyms = projectArticleWorkQueue(source, products, tasks, {
  isSuperuser: true, synonymAnalysis: {
    summary: { candidate_pairs: 1 },
    items: [
      { id: 'product-1', name: 'Melk', primary_gtin: '8712345678901',
        pending: [{ id: 'product-2', name: 'Melk groen' }] },
      { id: 'product-2', name: 'Melk groen', pending: [{ id: 'product-1', name: 'Melk' }] },
    ],
  },
})
assert.equal(withSynonyms.counts.synonyms, 2)
assert.equal(withSynonyms.tasks.filter(task => task.type === 'synonyms').length, 2)
assert.equal(withSynonyms.tasks.find(task => task.key === 'synonyms:product-1').area, 'synonyms')
const withoutSynonymWriteRight = projectArticleWorkQueue(source, products, tasks, {
  synonymAnalysis: {
    summary: { candidate_pairs: 1 },
    items: [{ id: 'product-1', name: 'Melk',
      pending: [{ id: 'product-2', name: 'Melk groen' }] }],
  },
  canManageSynonyms: false,
})
assert.equal(withoutSynonymWriteRight.counts.synonyms, 0)
assert.throws(() => projectArticleWorkQueue(source, products, tasks, {
  synonymAnalysis: { summary: { candidate_pairs: 1 }, items: [] },
}), /ontbreken/)

// Server-side classification page 1 is interactive immediately; no hidden
// 100-item background waterfall, partial global counts or local-only filtering.
import { readFileSync } from 'node:fs'
const workspace = readFileSync(new URL('../src/features/externalDatabases/CombinedClassificationWorkspace.jsx', import.meta.url), 'utf8')
const pagination = readFileSync(new URL('../../backend/app/services/classification_server_paging_service.py', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../../backend/app/api/cbs_classification_routes.py', import.meta.url), 'utf8')
const table = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
for (const expected of [
  'const PAGE_SIZE = 8',
  'workqueue-page?',
  'workqueue-summary',
  'workqueue-ids?',
  'workqueue-selected-export',
  'serverSide',
  'filterState={filters} onFilterChange={updateFilter}',
  'sortState={sortState} onSortChange={updateSort}',
  'data={loading || error ? [] : products}',
  'const allTableSelected = filteredTotal > 0',
  'setSelectedIds((current) =>',
  'selectionAbortRef.current?.abort()',
  'onSaved={onClassificationSaved}',
  'onApplied={onClassificationSaved}',
  'pageCount={pageCount}',
  'classification-first-page-ready',
]) {
  assert.ok(workspace.includes(expected), 'Classificeren full server pagination: ' + expected)
}
assert.doesNotMatch(workspace, /items\.length < total/)
assert.doesNotMatch(workspace, /setProducts\(items\.slice\(0, 8\)\)/)
assert.match(table, /if \(serverSide\) return \[\.\.\.filteredData\]/)
assert.match(table, /serverSide \? data : data\.filter/)
assert.match(pagination, /MAX_EXPORT_IDS = 20000/)
assert.match(pagination, /LIMIT :limit OFFSET :offset/)
assert.match(pagination, /AND gp\.id IN :product_ids/)
assert.match(pagination, /WHERE \{where\}/)
assert.match(routes, /@router\.get\("\/workqueue-page"\)/)
assert.match(routes, /@router\.get\("\/workqueue-summary"\)/)
assert.match(routes, /@router\.get\("\/workqueue-ids"\)/)
assert.match(routes, /@router\.post\("\/workqueue-selected-export"\)/)
assert.match(routes, /_actor\("platform\.external_products\.view"\)/)
assert.match(workspace, /fetchAllMatchingIds\(filters, controller\.signal\)/)
assert.match(workspace, /product_ids: selectedIds/)
assert.match(workspace, /setAllFilterIds\(\{ key: filterKey, ids \}\)/)

console.log('ARTICLE_MANAGEMENT_WORKQUEUE_MODEL_GREEN')
