import assert from 'node:assert/strict'
import fs from 'node:fs'
import { buildJumboImportEnvelope } from '../src/features/storeConnections/jumboReceiptImport.js'
import { jumboDateWindow, selectJumboHistory, jumboDay, importJumboBatch } from '../src/features/storeConnections/jumboReceiptBatch.js'
import {
  JUMBO_BOOKMARKLET_VERSION,
  JUMBO_ORDERS_URL,
  JUMBO_POC_FRAGMENT_PREFIX,
  buildJumboPocBookmarklet,
  parseJumboReceiptLayout,
} from '../src/features/storeConnections/jumboReceiptPocBridge.js'

assert.equal(JUMBO_BOOKMARKLET_VERSION, 8)
assert.equal(JUMBO_ORDERS_URL, 'https://www.jumbo.com/bestellingen')
assert.equal(JUMBO_POC_FRAGMENT_PREFIX, '#jumbo-poc-v8=')

const syntheticLayout = JSON.stringify({
  documents: [{
    documents: [{
      printSections: [{
        textObjects: [{
          textLines: [
            { texts: [{ text: 'OMSCHRIJVING' }, { text: 'BEDRAG' }] },
            { texts: [{ text: '================' }] },
            { texts: [{ text: 'BANANEN' }, { text: '' }, { text: '0,94' }] },
            { texts: [{ text: '  2 X 0,94' }, { text: '1,88' }] },
            { texts: [{ text: 'KOFFIE' }, { text: 'P' }, { text: '4,99' }] },
            { texts: [{ text: 'STATIEGELD' }, { text: '0,25' }] },
            { texts: [{ text: 'Totaal' }, { text: '7,12' }] },
            { texts: [{ text: 'Betaald' }] },
            { texts: [{ text: 'PIN' }] },
            { texts: [{ text: 'Aantal artikelen: 4' }] },
          ],
        }],
      }],
    }],
  }],
})

const parsed = parseJumboReceiptLayout(syntheticLayout)
assert.equal(parsed.parseError, undefined)
assert.equal(parsed.items.length, 2)
assert.equal(parsed.items[0].name, 'BANANEN')
assert.equal(parsed.items[0].quantity, 2)
assert.equal(parsed.items[0].unitPrice, 0.94)
assert.equal(parsed.items[0].price, 1.88)
assert.equal(parsed.items[1].name, 'KOFFIE')
assert.equal(parsed.items[1].isPromo, true)
assert.equal(parsed.deposits.length, 1)
assert.equal(parsed.deposits[0].name, 'STATIEGELD')
assert.equal(parsed.total, 7.12)
assert.equal(parsed.paymentMethod, 'PIN')
assert.equal(parsed.itemCount, 4)

const bookmarklet = buildJumboPocBookmarklet('http://localhost:5176/instellingen/winkelkoppelingen')
assert.match(bookmarklet, /^javascript:/)
assert.doesNotThrow(() => new Function(bookmarklet.slice('javascript:'.length)), 'Jumbo favorite must be valid standalone JavaScript')

assert.ok(bookmarklet.includes('const jumboDay = function(value)'))
assert.ok(bookmarklet.includes('const jumboDateWindow = function(from, to)'))
assert.ok(bookmarklet.includes('const selectJumboHistory = function(receipts, from, to'))
assert.ok(!bookmarklet.includes('tf('), 'The Jumbo favorite must not refer to minified helper names')
const bridgeSource = fs.readFileSync(new URL('../src/features/storeConnections/jumboReceiptPocBridge.js', import.meta.url), 'utf8')
assert.ok(!bridgeSource.includes('parseJumboReceiptLayout.toString()'), 'Bookmarklet parser must not depend on minifier output')
for (const helper of ['jumboDay', 'jumboDateWindow', 'selectJumboHistory']) {
  assert.ok(!bridgeSource.includes(helper + '.toString()'), 'No minifier-dependent helper: ' + helper)
}
assert.match(bookmarklet, /\/api\/graphql/)
assert.match(bookmarklet, /GetOnlineOrdersAndStoreReceipts/)
assert.match(bookmarklet, /GetDigitalReceipt/)
assert.match(bookmarklet, /receiptOverview/)
assert.match(bookmarklet, /receiptImage/)
assert.match(bookmarklet, /OMSCHRIJVING/)
assert.match(bookmarklet, /Betaald/)
assert.match(bookmarklet, /credentials:"include"/)
assert.match(bookmarklet, /JUMBO_WEB-orders/)
assert.match(bookmarklet, /#jumbo-poc-v8=/)
assert.match(bookmarklet, /location\.href=C\+P/)
assert.match(bookmarklet, /source_origin:location\.origin/)
assert.doesNotMatch(bookmarklet, /window\.opener/)
assert.doesNotMatch(bookmarklet, /postMessage/)
assert.doesNotMatch(bookmarklet, /inhuis:jumbo-poc-handshake/)
assert.doesNotMatch(bookmarklet, /BOOKMARKLET_START/)
assert.doesNotMatch(bookmarklet, /HANDSHAKE_SENT/)
assert.doesNotMatch(bookmarklet, /document\.cookie/)
assert.doesNotMatch(bookmarklet, /localStorage/)
assert.doesNotMatch(bookmarklet, /sessionStorage/)
assert.doesNotMatch(bookmarklet, /password/i)

const storeConnectionsSource = fs.readFileSync(
  new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url),
  'utf8',
)
assert.match(storeConnectionsSource, /JUMBO_POC_FRAGMENT_PREFIX/)
assert.match(storeConnectionsSource, /decodeURIComponent\(encoded\)/)
assert.match(storeConnectionsSource, /window\.history\.replaceState/)
assert.match(storeConnectionsSource, /redirectmethode/)
assert.match(storeConnectionsSource, /URL-fragment/)
assert.match(storeConnectionsSource, /Ontlede productregels/)
assert.match(storeConnectionsSource, /Betaalwijze/)
assert.match(storeConnectionsSource, /Geen \(nieuwe\) kassabonnen gevonden\./)
assert.doesNotMatch(storeConnectionsSource, /buildJumboPocPageScript/)
assert.doesNotMatch(storeConnectionsSource, /jumbo-poc-diagnostics/)
assert.doesNotMatch(storeConnectionsSource, /SOURCE_MISMATCH/)
assert.doesNotMatch(storeConnectionsSource, /HANDSHAKE_OK/)
assert.doesNotMatch(storeConnectionsSource, /sampleReceipt/)
assert.doesNotMatch(storeConnectionsSource, /v4-knop/)
assert.doesNotMatch(storeConnectionsSource, /JUMBO_WEB_ORIGIN/)
const jumboLaunch = storeConnectionsSource.slice(
  storeConnectionsSource.indexOf('href={JUMBO_ORDERS_URL}'),
  storeConnectionsSource.indexOf('data-testid="jumbo-poc-open"'),
)
assert.match(jumboLaunch, /role="button"/)
assert.match(jumboLaunch, /className="rz-button-primary"/)
const jumboButtonCss = fs.readFileSync(new URL('../src/ui/components/button.css', import.meta.url), 'utf8')
assert.match(jumboButtonCss, /a\.rz-button-primary\[role="button"\]/)
assert.match(jumboLaunch, /target="_blank"/)
assert.match(jumboLaunch, /rel="noopener noreferrer"/)
assert.ok(storeConnectionsSource.includes('Open mijn Jumbo (nieuw tabblad)'))
assert.ok(!storeConnectionsSource.includes('window.location.assign(JUMBO_ORDERS_URL)'))
assert.doesNotMatch(storeConnectionsSource, /window\.open\(JUMBO_ORDERS_URL/)
assert.doesNotMatch(storeConnectionsSource, /window\.opener/)
// The Lidl bridge legitimately uses postMessage; isolate the Jumbo redirect handler.
const jumboHandler = storeConnectionsSource.slice(
  storeConnectionsSource.indexOf("const hash = String(window.location.hash || '')"),
  storeConnectionsSource.indexOf('async function startAhLogin()'),
)
assert.doesNotMatch(jumboHandler, /postMessage/)

// Synthetic receipt tests: no real Jumbo account or database is touched.
const observation = {
  version: JUMBO_BOOKMARKLET_VERSION,
  ok: true,
  source_origin: 'https://www.jumbo.com',
  first_detail: {
    transactionId: 'TXN-20261013-01',
    purchaseEndOn: '2026-10-13T12:30:00',
    storeName: 'Jumbo Test',
    parsed,
  },
}
const envelope = buildJumboImportEnvelope(observation)
assert.equal(envelope.provider, 'jumbo')
assert.equal(envelope.external_receipt_id, 'TXN-20261013-01')
assert.equal(envelope.schema_version, '1.0')
assert.equal(envelope.receipt.items.length, 3)
assert.equal(envelope.receipt.items[0].quantity, 2)
assert.equal(envelope.receipt.items[0].lineTotal, 1.88)
assert.equal(envelope.receipt.items[2].lineType, 'deposit')
assert.equal(envelope.receipt.grandTotal, 7.12)
assert.deepEqual(Object.keys(envelope).sort(), ['external_receipt_id', 'provider', 'receipt', 'schema_version'])
const rejected = (obj) => assert.throws(() => buildJumboImportEnvelope(obj), Error)
rejected({ ...observation, source_origin: 'https://jumbo.com' })
rejected({ ...observation, source_origin: 'https://evil.example' })
rejected({ ...observation, ok: false })
rejected({ ...observation, version: 5 })
rejected({ ...observation, version: 6 }) // obsolete favorite must fail closed
rejected({ ...observation, version: 7 }) // production syntax bug in v7
rejected({ ...observation, first_detail: null })
rejected({ ...observation, first_detail: { ...observation.first_detail, transactionId: '' } })
rejected({ ...observation, first_detail: { ...observation.first_detail, purchaseEndOn: '' } })
rejected({ ...observation, first_detail: { ...observation.first_detail, parsed: { ...parsed, items: [] } } })
rejected({ ...observation, first_detail: { ...observation.first_detail, parsed: { ...parsed, total: 7.13 + 0.02 } } })
rejected({ ...observation, first_detail: { ...observation.first_detail, parsed: { ...parsed, parseError: 'invalid' } } })
const ui = storeConnectionsSource
assert.match(ui, /importJumboBatch\(/)
assert.match(ui, /buildJumboImportEnvelope,/)
assert.match(ui, /jumbo-confirm-import/)
assert.match(ui, /fetchJson\('\/api\/receipts\/retailers\/import'/)
assert.match(ui, /setJumboImportCandidate\(null\)/)
assert.match(ui, /importJumboBatch\(/)
assert.match(ui, /jumbo-from-date/)
assert.match(ui, /jumbo-to-date/)
assert.match(bookmarklet, /Jumbo geschiedenis ophalen/)
assert.match(bookmarklet, /selectJumboHistory/)
assert.match(bookmarklet, /MAX_PAGES/)
assert.match(bookmarklet, /Jumbo-paginering wijkt af/)
assert.match(bookmarklet, /location\.href=C\+P/)

console.log('JUMBO_RECEIPT_REDIRECT_DETAIL_POC_CONTRACT_GREEN')

assert.equal(jumboDay('2026-02-30'), '')
assert.equal(jumboDay('2026-10-13T09:00:00'), '2026-10-13')
assert.deepEqual(jumboDateWindow('2026-10-01','2026-10-13'), { from_date: '2026-10-01', to_date: '2026-10-13' })
assert.throws(() => jumboDateWindow('2026-10-13','2026-10-01'))
assert.throws(() => jumboDateWindow('2026-02-30','2026-10-01'))
const history = [
  { transactionId:'TX-001', purchaseEndOn:'2026-09-09T14:00:00' },
  { transactionId:'TX-002', purchaseEndOn:'2026-08-25T14:00:00' },
  { transactionId:'TX-003', purchaseEndOn:'2026-07-01T14:00:00' },
]
assert.equal(selectJumboHistory(history, '2026-08-01', '2026-09-30').length, 2)
assert.equal(selectJumboHistory(history, '2026-08-25', '2026-08-25')[0].transactionId, 'TX-002')
assert.throws(() => selectJumboHistory([...history, history[0]], '2026-08-01', '2026-09-30'))
assert.throws(() => selectJumboHistory(history, '2026-08-01', '2026-09-30', 1))
assert.throws(() => selectJumboHistory([{ transactionId:'BAD', purchaseEndOn:'unknown' }], '2026-08-01', '2026-09-30'))
const second = { ...observation.first_detail, transactionId: 'TXN-20261013-02' }
const batch = { ...observation, details: [observation.first_detail, second] }
const imported = []
const counts = await importJumboBatch(batch, async (env) => {
  imported.push(env.external_receipt_id)
  return imported.length === 1 ? { duplicate: false, raw_receipt_id: 'receipt1' } : { duplicate: true }
}, buildJumboImportEnvelope)
assert.deepEqual(counts, { new: 1, known: 1, refreshed: 0, failed: 0 })
assert.deepEqual(imported, ['TXN-20261013-01', 'TXN-20261013-02'])
await assert.rejects(() => importJumboBatch({ ...batch, details: [observation.first_detail, observation.first_detail] }, async () => { throw new Error('Should never write') }, buildJumboImportEnvelope))
let countProcessed = 0
await assert.rejects(
  () => importJumboBatch(batch, async () => {
    countProcessed++
    if (countProcessed === 2) throw new Error('Network interrupted')
    return { duplicate: false, raw_receipt_id: 'receipt1' }
  }, buildJumboImportEnvelope),
  (error) => error.jumboProcessed === 1 && error.jumboCounts.failed === 1,
)
console.log('JUMBO_BATCH_IMPORT_FAIL_CLOSED_GREEN')
