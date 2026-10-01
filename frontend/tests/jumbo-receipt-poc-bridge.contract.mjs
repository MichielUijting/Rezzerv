import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  JUMBO_BOOKMARKLET_VERSION,
  JUMBO_ORDERS_URL,
  JUMBO_WEB_ORIGIN,
  buildJumboPocBookmarklet,
  buildJumboPocPageScript,
} from '../src/features/storeConnections/jumboReceiptPocBridge.js'

assert.equal(JUMBO_WEB_ORIGIN, 'https://www.jumbo.com')
assert.equal(JUMBO_BOOKMARKLET_VERSION, 3)
assert.equal(JUMBO_ORDERS_URL, 'https://www.jumbo.com/bestellingen')
assert.doesNotMatch(JUMBO_ORDERS_URL, /\/account\/inloggen/)
assert.doesNotMatch(JUMBO_ORDERS_URL, /\/mijn-jumbo\/bestellingen/)

const bookmarklet = buildJumboPocBookmarklet()
assert.match(bookmarklet, /^javascript:/)
assert.match(bookmarklet, /window\.opener/)
assert.match(bookmarklet, /inhuis:jumbo-poc-handshake/)
assert.match(bookmarklet, /BOOKMARKLET_START/)
assert.match(bookmarklet, /HANDSHAKE_SENT/)
assert.match(bookmarklet, /WINDOW_OPENER/)
assert.match(bookmarklet, /__inhuis_jumbo_poc_diag/)
assert.match(bookmarklet, /HANDSHAKE_SENT: ja/)
assert.match(bookmarklet, /INHUIS_ANTWOORD/)
assert.match(bookmarklet, /\[Inhuis Jumbo POC\]/)
assert.match(bookmarklet, /bookmarklet_version/)
assert.doesNotMatch(bookmarklet, /localhost:5174/)
assert.match(bookmarklet, /W\.postMessage\([^;]+,"\*"\)/)
assert.match(bookmarklet, /e\.source!==W/)
assert.match(bookmarklet, /e\.origin/)
assert.doesNotMatch(bookmarklet, /document\.cookie/)
assert.doesNotMatch(bookmarklet, /localStorage/)
assert.doesNotMatch(bookmarklet, /sessionStorage/)
assert.doesNotMatch(bookmarklet, /password/i)

const script = buildJumboPocPageScript('http://localhost:5174')
assert.match(script, /\/api\/graphql/)
assert.match(script, /GetOnlineOrdersAndStoreReceipts/)
assert.match(script, /GetDigitalReceipt/)
assert.match(script, /RUNNER_START/)
assert.match(script, /GRAPHQL_LIST_START/)
assert.match(script, /GRAPHQL_LIST_OK/)
assert.match(script, /receiptOverview/)
assert.match(script, /receipt\(transactionId:/)
assert.match(script, /credentials:\s*'include'/)
assert.match(script, /JUMBO_WEB-orders/)
assert.match(script, /AbortController/)
assert.match(script, /20000/)
assert.match(script, /reageerde niet binnen 20 seconden/)
assert.match(script, /inhuis:jumbo-poc-result/)
assert.match(script, /layoutProof/)
assert.match(script, /hasItemsHeader/)
assert.match(script, /hasTotalLine/)
assert.doesNotMatch(script, /document\.cookie/)
assert.doesNotMatch(script, /localStorage/)
assert.doesNotMatch(script, /sessionStorage/)
assert.doesNotMatch(script, /password/i)

const storeConnectionsSource = fs.readFileSync(
  new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url),
  'utf8',
)
assert.match(storeConnectionsSource, /Geen \(nieuwe\) kassabonnen gevonden\./)
assert.match(storeConnectionsSource, /Jumbo is geopend\. Log zo nodig in/)
assert.doesNotMatch(storeConnectionsSource, /setJumboPocProgress\('Jumbo openen…'\)/)
assert.match(storeConnectionsSource, /jumbo-poc-diagnostics/)
assert.match(storeConnectionsSource, /ORIGIN_MISMATCH/)
assert.match(storeConnectionsSource, /SOURCE_MISMATCH/)
assert.match(storeConnectionsSource, /VERSION_MISMATCH/)
assert.match(storeConnectionsSource, /POPUP_BLOCKED/)
assert.match(storeConnectionsSource, /WINDOW_REF_OK/)
assert.match(storeConnectionsSource, /GEEN_INBOUND_MESSAGE/)
assert.match(storeConnectionsSource, /raw message/)

console.log('JUMBO_RECEIPT_POC_BRIDGE_CONTRACT_GREEN')
