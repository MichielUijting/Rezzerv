import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(
  new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url),
  'utf8',
)

const sync = source.split('async function syncSelectedReviewDecisions(selectedIds) {')[1]
  ?.split('\n  async function handleProcessSelected(')[0]
assert.ok(sync, 'Bulkselectie moet expliciet worden doorgegeven')
assert.match(sync, /selectedSet\.has\(String\(line\.id\)\)/)
assert.match(sync, /processing_status.*processed/)
assert.match(sync, /review_decision: 'selected'/)
assert.doesNotMatch(sync, /review_decision: 'ignored'/, 'Niet-aangevinkte regels mogen niet automatisch genegeerd worden')
assert.doesNotMatch(sync, /: 'ignored'/, 'Bulkactie mag niet ongevraagde ignore-statussen schrijven')

const handle = source.split('async function handleProcessSelected(mode = ')[1]
  ?.split('\n  function handlePrimaryProcessClick')[0]
assert.ok(handle)
assert.match(handle, /const selectedIds = \[\.\.\.new Set\(selectedLineIds\.map\(String\)\)\]/)
assert.match(handle, /syncSelectedReviewDecisions\(selectedIds\)/)
assert.match(handle, /processBatchNow\(mode, selectedIds, refreshed\)/)

const processor = source.split('async function processBatchNow(')[1]
  ?.split('\n  const diagByLineId')[0]
assert.ok(processor)
assert.match(processor, /new Set\(selectedIds\.map\(String\)\)/)
assert.match(processor, /currentBatch\.lines/)
assert.doesNotMatch(processor, /lines: \(current\.lines \|\| \[\]\)\.filter/, 'Geen tijdelijke bronregelverwijdering voordat de server is ververst')

console.log('Uitpakken bulkselectie contract: OK')
