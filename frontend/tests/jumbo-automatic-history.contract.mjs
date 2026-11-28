import assert from 'node:assert/strict'
import { JUMBO_BATCH_LIMIT, JUMBO_MAX_PAGES, planJumboHistoricalBatches } from '../src/features/storeConnections/jumboReceiptBatch.js'
import { buildJumboPocBookmarklet } from '../src/features/storeConnections/jumboReceiptPocBridge.js'
import { buildUniversalRetailerBookmarklet } from '../src/features/storeConnections/universalRetailerBookmarklet.js'
import { buildLidlWebBookmarklet } from '../src/features/storeConnections/lidlWebReceiptBridge.js'
import { readFileSync } from 'node:fs'

assert.equal(JUMBO_BATCH_LIMIT, 10, 'The existing ten-receipt protection is never relaxed')
assert.equal(JUMBO_MAX_PAGES, 200)
const period = { from_date: '2025-01-01', to_date: '2026-11-25' }
const day = (date, id) => ({ transactionId: 'JUMBO-' + String(id).padStart(4, '0'), purchaseEndOn: date })
const receipts = [
  day('2024-12-31', 1),
  ...Array.from({ length: 22 }, (_, i) => day('2025-01-01', i + 2)),
  day('2025-02-01', 24), day('2026-11-25', 25), day('2026-11-26', 26),
]
const batches = planJumboHistoricalBatches(receipts, period.from_date, period.to_date)
assert.deepEqual(batches.map(b => b.receipts.length), [10, 10, 2, 1, 1])
assert.equal(batches[0].month, '2025-01')
assert.equal(batches.at(-1).month, '2026-11')
assert.equal(batches.reduce((n, batch) => n + batch.receipts.length, 0), 24)
assert.ok(batches.every(batch => batch.receipts.length <= 10))
assert.equal(new Set(batches.flatMap(b => b.receipts.map(r => r.transactionId))).size, 24)
assert.throws(() => planJumboHistoricalBatches([...receipts, receipts[3]], ...Object.values(period)),
  /Dubbel Jumbo-bonnummer/)
assert.throws(() => planJumboHistoricalBatches([day('2025-02-30', 1)], ...Object.values(period)),
  /aankoopdatum/)
assert.throws(() => planJumboHistoricalBatches(Array.from({ length: 2001 }, (_, i) =>
  day('2025-01-01', i)), ...Object.values(period)), /groter/)
assert.deepEqual(planJumboHistoricalBatches([], period.from_date, period.to_date), [])

const options = { automatic: true, requestId: '1764200000000-abcdef123', inhuisOrigin: 'https://inhuis.example' }
const auto = decodeURIComponent(buildJumboPocBookmarklet('https://inhuis.example/onboarding/winkels',
  period, options).slice('javascript:'.length))
assert.doesNotThrow(() => new Function(auto), 'The browser script must compile without bundler dependencies')
assert.match(auto, /inhuis:jumbo-batch/)
assert.match(auto, /inhuis:jumbo-ack/)
assert.match(auto, /inhuis:jumbo-complete/)
assert.match(auto, /total_receipts:total/)
assert.match(auto, /MAX_PAGES\*10/)
assert.match(auto, /selectJumboHistory\(receipts\.slice/)
assert.match(auto, /window\.opener/)
assert.match(auto, /event\.source!==opener/)
assert.match(auto, /details\.length/)
assert.doesNotMatch(auto, /location\.href=C\+P\+encodeURIComponent\(JSON\.stringify\(\{type:"inhuis:jumbo-batch"/)
assert.throws(() => buildJumboPocBookmarklet('https://inhuis.example/', period,
  { automatic: true, requestId: 'invalid', inhuisOrigin: 'https://inhuis.example' }), /handshake/)

const legacy = decodeURIComponent(buildJumboPocBookmarklet('https://inhuis.example/onboarding/winkels',
  period).slice('javascript:'.length))
assert.doesNotThrow(() => new Function(legacy))
assert.match(legacy, /jumbo-poc-v14/)
assert.match(legacy, /selectJumboHistory\(history,RANGE.from_date,RANGE.to_date,LIMIT\)/)
const universal = buildUniversalRetailerBookmarklet('https://inhuis.example',
  buildLidlWebBookmarklet('https://inhuis.example'))
assert.match(universal, /^javascript:/)
assert.doesNotMatch(universal, /2025-01-01/)
assert.doesNotMatch(universal, /2026-11-25/)

const page = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
const backend = readFileSync(new URL('../../backend/app/services/jumbo_history_import_service.py', import.meta.url), 'utf8')
assert.match(page, /jumbo\/history\/begin/)
assert.match(page, /jumbo\/history\/complete/)
assert.match(page, /stageJumboBatch\(/)
assert.match(page, /run\.seen\.has\(id\)/)
assert.match(page, /event\.origin !== JUMBO_WEB_ORIGIN/)
assert.match(backend, /pending_from_date/)
assert.match(backend, /scan_complete/)
assert.match(backend, /_queue_completed/)
console.log('JUMBO_AUTOMATIC_HISTORY_CONTRACT_GREEN')
