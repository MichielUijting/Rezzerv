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

console.log('ARTICLE_MANAGEMENT_WORKQUEUE_MODEL_GREEN')
