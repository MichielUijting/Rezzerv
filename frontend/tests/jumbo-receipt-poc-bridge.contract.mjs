import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  JUMBO_BOOKMARKLET_VERSION,
  JUMBO_ORDERS_URL,
  JUMBO_POC_FRAGMENT_PREFIX,
  buildJumboPocBookmarklet,
} from '../src/features/storeConnections/jumboReceiptPocBridge.js'

assert.equal(JUMBO_BOOKMARKLET_VERSION, 4)
assert.equal(JUMBO_ORDERS_URL, 'https://www.jumbo.com/bestellingen')
assert.equal(JUMBO_POC_FRAGMENT_PREFIX, '#jumbo-poc-v4=')

const bookmarklet = buildJumboPocBookmarklet('http://localhost:5176/instellingen/winkelkoppelingen')
assert.match(bookmarklet, /^javascript:/)
assert.match(bookmarklet, /\/api\/graphql/)
assert.match(bookmarklet, /GetOnlineOrdersAndStoreReceipts/)
assert.match(bookmarklet, /receiptOverview/)
assert.match(bookmarklet, /credentials:"include"/)
assert.match(bookmarklet, /JUMBO_WEB-orders/)
assert.match(bookmarklet, /#jumbo-poc-v4=/)
assert.match(bookmarklet, /location\.href=C\+P/)
assert.match(bookmarklet, /source_origin:location\.origin/)
assert.doesNotMatch(bookmarklet, /window\.opener/)
assert.doesNotMatch(bookmarklet, /postMessage/)
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
assert.match(storeConnectionsSource, /zonder window\.opener/)
assert.match(storeConnectionsSource, /URL-fragment/)
assert.match(storeConnectionsSource, /Geen \(nieuwe\) kassabonnen gevonden\./)
assert.doesNotMatch(storeConnectionsSource, /JUMBO_WEB_ORIGIN/)
assert.doesNotMatch(storeConnectionsSource, /buildJumboPocPageScript/)
assert.doesNotMatch(storeConnectionsSource, /jumbo-poc-diagnostics/)
assert.doesNotMatch(storeConnectionsSource, /SOURCE_MISMATCH/)
assert.doesNotMatch(storeConnectionsSource, /HANDSHAKE_OK/)

console.log('JUMBO_RECEIPT_REDIRECT_POC_CONTRACT_GREEN')
