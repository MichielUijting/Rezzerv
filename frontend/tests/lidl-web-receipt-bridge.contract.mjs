import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  LIDL_BOOKMARKLET_VERSION,
  LIDL_HISTORY_URL,
  LIDL_WEB_ORIGIN,
  buildLidlWebBookmarklet,
  buildLidlWebPageScript,
} from '../src/features/storeConnections/lidlWebReceiptBridge.js'

assert.equal(LIDL_WEB_ORIGIN, 'https://www.lidl.nl')
assert.equal(LIDL_BOOKMARKLET_VERSION, 2)
assert.match(LIDL_HISTORY_URL, /\/mre\/purchase-history/)
assert.match(LIDL_HISTORY_URL, /client_id=NetherlandsEcommerceClient/)

const bookmarklet = buildLidlWebBookmarklet('http://localhost:5174')
assert.match(bookmarklet, /^javascript:/)
assert.match(bookmarklet, /http:\/\/localhost:5174/)
assert.match(bookmarklet, /window\.opener/)
assert.match(bookmarklet, /inhuis:lidl-handshake/)
assert.match(bookmarklet, /bookmarklet_version/)
assert.doesNotMatch(bookmarklet, /lidlImport=1/)
assert.doesNotMatch(bookmarklet, /window\.open\s*\(/)

const script = buildLidlWebPageScript('http://localhost:5174')
assert.match(script, /\/mre\/purchase-history/)
assert.match(script, /window\.opener/)
assert.doesNotMatch(script, /window\.open\s*\(/)
assert.match(script, /\/mre\/purchase-detail/)
assert.match(script, /NetherlandsEcommerceClient/)
assert.match(script, /data-art-description/)
assert.match(script, /structuredArticleSpan/)
assert.match(script, /spans\.find/)
assert.match(script, /extractionDiagnostics/)
assert.match(script, /expectedArticleCount/)
assert.doesNotMatch(script, /startsWith\(description\)/)
assert.match(script, /artQuantity/)
assert.match(script, /unitPrice/)
assert.match(script, /artId/)
assert.match(script, /data-tax-type/)
assert.match(script, /taxPercentage/)
assert.match(script, /statiegeld|deposit|pfand/)
assert.match(script, /discountTotal/)
assert.match(script, /depositTotal/)
assert.match(script, /paymentMethod/)
assert.match(script, /codeInput/)
assert.match(script, /retailerSku/)
assert.match(script, /packageSize/)
assert.match(script, /inhuis:lidl-receipt/)
assert.match(script, /inhuis:lidl-complete/)
assert.match(script, /_sourceSnapshotDataUrl/)
assert.match(script, /toDataURL\('image\/png'\)/)
assert.doesNotMatch(script, /document\.cookie/)
assert.doesNotMatch(script, /localStorage/)
assert.doesNotMatch(script, /sessionStorage/)
assert.doesNotMatch(script, /Password|password/)

const windowedScript = buildLidlWebPageScript('http://localhost:5174', {
  from_date: '2026-10-01', to_date: '2026-10-11',
})
assert.match(windowedScript, /2026-10-01/)
assert.match(windowedScript, /2026-10-11/)
assert.match(windowedScript, /withinWindow\(rowDate\)/)
assert.match(windowedScript, /withinWindow\(receipt.dateTime\)/)
assert.match(windowedScript, /fromDate/)
assert.match(windowedScript, /toDate/)

console.log('LIDL_WEB_RECEIPT_BRIDGE_CONTRACT_GREEN')

// A single old purchase-detail remains available outside the automatic window.
assert.match(windowedScript, /isHistory && matchesWindow !== true/)
assert.match(windowedScript, /orderedPages >= 2/)
assert.match(windowedScript, /pageNumber === 50/)
assert.match(windowedScript, /if \(pageNumber === 1\) throw new Error\('Lidl-historie kon niet worden geladen/)

assert.match(windowedScript, /last_imported_date/)
assert.match(windowedScript, /await waitForAck\(receipt.id\)/)



// Regression: the Lidl history UI renders '9 september' without a year.
// Resolve the year from the preceding month heading before applying the
// import window. Unknown years must fail closed instead of scanning 75 rows.
const normalizeSource = windowedScript.slice(
  windowedScript.indexOf('function normalizeDay('),
  windowedScript.indexOf('function withinWindow('),
)
const historySource = windowedScript.slice(
  windowedScript.indexOf('function historyRowDay('),
  windowedScript.indexOf('function parseDateTime('),
)
assert.ok(normalizeSource.includes('function normalizeDay('))
assert.ok(historySource.includes('function historyRowDay('))
const parseHistoryDay = new Function('clean', 'Node',
  normalizeSource + historySource + 'return historyRowDay;')(
  value => String(value || '').replace(/\\s+/g, ' ').trim(),
  { DOCUMENT_POSITION_FOLLOWING: 4 },
)
function historyFixture(row, heading) {
  const anchor = {
    querySelector: () => ({ textContent: row }),
  }
  const doc = {
    querySelectorAll: () => heading === null ? [] : [{
      textContent: heading,
      compareDocumentPosition: node => node === anchor ? 4 : 0,
    }],
  }
  return { anchor, doc }
}
{
  const { anchor, doc } = historyFixture('9 september', 'September 2026')
  assert.equal(parseHistoryDay(anchor, doc), '2026-09-09')
}
{
  const { anchor, doc } = historyFixture('25 augustus', 'Augustus 2026')
  assert.equal(parseHistoryDay(anchor, doc), '2026-08-25')
}
{
  const { anchor, doc } = historyFixture('9 september', null)
  assert.throws(() => parseHistoryDay(anchor, doc), /Jaartal ontbreekt/)
}
assert.match(windowedScript, /anchors\.map\(anchor => historyRowDay\(/)
assert.match(windowedScript, /withinWindow\(rowDate\) !== true/)
assert.match(windowedScript, /entries\.length \+ ' bonnen binnen de ingestelde periode gevonden/)
console.log('LIDL_HISTORY_YEAR_FILTER_REGRESSION_GREEN')

// The PO cannot start a Lidl history import with unsaved date edits.
const storeConnectionScreen = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
assert.match(storeConnectionScreen, /const lidlPeriodUnsaved =/)
assert.match(storeConnectionScreen, /lidlFrom !== \(lidlWindow\.configured_from_date/)
assert.match(storeConnectionScreen, /data-testid="lidl-period-unsaved"/)
assert.match(storeConnectionScreen, /disabled=\{lidlPeriodUnsaved \|\| lidlWindowSaving \|\| !lidlWindow\}/)
console.log('LIDL_UNSAVED_PERIOD_GUARD_GREEN')
