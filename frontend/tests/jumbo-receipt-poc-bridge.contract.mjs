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

assert.equal(JUMBO_BOOKMARKLET_VERSION, 12)
assert.equal(JUMBO_ORDERS_URL, 'https://www.jumbo.com/bestellingen')
assert.equal(JUMBO_POC_FRAGMENT_PREFIX, '#jumbo-poc-v12=')

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
assert.ok(!/[\r\n\t]/.test(bookmarklet), 'Firefox bookmarklets must not contain literal newlines or tabs')
const bookmarkletBody = decodeURIComponent(bookmarklet.slice('javascript:'.length))
assert.match(bookmarkletBody, /function parseReceipt/)
assert.doesNotThrow(() => new Function(decodeURIComponent(bookmarklet.replace(/[\r\n\t]/g, '').slice('javascript:'.length))), 'Document URL normalization must preserve syntax in encoded favorite')
assert.doesNotThrow(() => new Function(decodeURIComponent(bookmarklet.slice('javascript:'.length))), 'Jumbo favorite must be valid standalone JavaScript')

assert.ok(bookmarkletBody.includes('const jumboDay = function(value)'))
assert.ok(bookmarkletBody.includes('const jumboDateWindow = function(from, to)'))
assert.ok(bookmarkletBody.includes('const selectJumboHistory = function(receipts, from, to'))
assert.ok(!bookmarkletBody.includes('tf('), 'The Jumbo favorite must not refer to minified helper names')
const bridgeSource = fs.readFileSync(new URL('../src/features/storeConnections/jumboReceiptPocBridge.js', import.meta.url), 'utf8')
assert.ok(!bridgeSource.includes('parseJumboReceiptLayout.toString()'), 'Bookmarklet parser must not depend on minifier output')
for (const helper of ['jumboDay', 'jumboDateWindow', 'selectJumboHistory']) {
  assert.ok(!bridgeSource.includes(helper + '.toString()'), 'No minifier-dependent helper: ' + helper)
}
assert.match(bookmarkletBody, /\/api\/graphql/)
assert.match(bookmarkletBody, /GetOnlineOrdersAndStoreReceipts/)
assert.match(bookmarkletBody, /GetDigitalReceipt/)
assert.match(bookmarkletBody, /receiptOverview/)
assert.match(bookmarkletBody, /receiptImage/)
assert.match(bookmarkletBody, /OMSCHRIJVING/)
assert.match(bookmarkletBody, /Betaald/)
assert.match(bookmarkletBody, /credentials:"include"/)
assert.match(bookmarkletBody, /JUMBO_WEB-orders/)
assert.match(bookmarkletBody, /#jumbo-poc-v12=/)
assert.match(bookmarkletBody, /location\.href=C\+P/)
assert.match(bookmarkletBody, /source_origin:location\.origin/)
assert.doesNotMatch(bookmarkletBody, /window\.opener/)
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
assert.doesNotMatch(jumboLaunch, /target="_blank"/)
assert.doesNotMatch(jumboLaunch, /rel="noopener noreferrer"/)
assert.ok(storeConnectionsSource.includes('Open mijn Jumbo (zelfde tabblad)'))
assert.ok(storeConnectionsSource.includes('daarna keer je terug in hetzelfde tabblad') || storeConnectionsSource.includes('Daarna keer je terug in hetzelfde tabblad'))
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
const punctuatedObservation = {
  ...observation,
  first_detail: { ...observation.first_detail, transactionId: 'ABC:123.2026/01' },
}
const punctuatedEnvelope = buildJumboImportEnvelope(punctuatedObservation)
assert.equal(punctuatedEnvelope.external_receipt_id, 'ABC:123.2026/01')
assert.throws(
  () => buildJumboImportEnvelope({ ...observation, first_detail: { ...observation.first_detail, transactionId: 'BAD ID' } }),
  /bonnummer/
)
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
rejected({ ...observation, version: 8 }) // Firefox strips raw newline bytes from v8
rejected({ ...observation, version: 9 }) // previous bookmarklet version
rejected({ ...observation, version: 10 }) // previous diagnostic version
rejected({ ...observation, version: 11 }) // obsolete strict ID limitation
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
assert.match(bookmarkletBody, /Jumbo geschiedenis ophalen/)
assert.match(bookmarkletBody, /selectJumboHistory/)
assert.match(bookmarkletBody, /MAX_PAGES/)
assert.match(bookmarkletBody, /Jumbo-paginering wijkt af/)
assert.match(bookmarkletBody, /location\.href=C\+P/)

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
assert.throws(
  () => selectJumboHistory([{ transactionId: null, purchaseEndOn: '2026-09-01T12:00:00' }], '2026-08-01', '2026-09-30'),
  /regel 1: bonnummer ontbreekt/
)
assert.throws(
  () => selectJumboHistory([{ transactionId: 'SENSITIVE WITH SPACE', purchaseEndOn: '2026-09-01T12:00:00' }], '2026-08-01', '2026-09-30'),
  error => /bonnummer heeft een onverwacht formaat/.test(error.message) && !error.message.includes('SENSITIVE')
)
assert.deepEqual(
  selectJumboHistory([{ transactionId: 'VALID:123/01', purchaseEndOn: '2026-09-01T12:00:00' }], '2026-08-01', '2026-09-30').map(row => row.transactionId),
  ['VALID:123/01']
)
assert.throws(
  () => selectJumboHistory([{ transactionId: 'a.b', purchaseEndOn: '2026-09-01T12:00:00' }], '2026-08-01', '2026-09-30'),
  /te kort/
)
assert.throws(
  () => selectJumboHistory([{ transactionId: 'LONG PRIVATE ID WITH SPACE', purchaseEndOn: '2026-09-01T12:00:00' }], '2026-08-01', '2026-09-30'),
  error => /bevat spaties of witruimte/.test(error.message) && !error.message.includes('LONG PRIVATE')
)

assert.throws(
  () => selectJumboHistory([{ transactionId: 'JUMBO-12345', purchaseEndOn: null }], '2026-08-01', '2026-09-30'),
  /aankoopdatum ontbreekt of is ongeldig/
)
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
