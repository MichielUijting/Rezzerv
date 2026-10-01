import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  JUMBO_BOOKMARKLET_VERSION,
  JUMBO_ORDERS_URL,
  JUMBO_POC_FRAGMENT_PREFIX,
  buildJumboPocBookmarklet,
  parseJumboReceiptLayout,
} from '../src/features/storeConnections/jumboReceiptPocBridge.js'

assert.equal(JUMBO_BOOKMARKLET_VERSION, 5)
assert.equal(JUMBO_ORDERS_URL, 'https://www.jumbo.com/bestellingen')
assert.equal(JUMBO_POC_FRAGMENT_PREFIX, '#jumbo-poc-v5=')

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
assert.match(bookmarklet, /\/api\/graphql/)
assert.match(bookmarklet, /GetOnlineOrdersAndStoreReceipts/)
assert.match(bookmarklet, /GetDigitalReceipt/)
assert.match(bookmarklet, /receiptOverview/)
assert.match(bookmarklet, /receiptImage/)
assert.match(bookmarklet, /OMSCHRIJVING/)
assert.match(bookmarklet, /Betaald/)
assert.match(bookmarklet, /credentials:"include"/)
assert.match(bookmarklet, /JUMBO_WEB-orders/)
assert.match(bookmarklet, /#jumbo-poc-v5=/)
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
assert.match(storeConnectionsSource, /window\.location\.assign\(JUMBO_ORDERS_URL\)/)
assert.doesNotMatch(storeConnectionsSource, /window\.open\(JUMBO_ORDERS_URL/)
assert.doesNotMatch(storeConnectionsSource, /window\.opener/)
assert.doesNotMatch(storeConnectionsSource, /postMessage/)

console.log('JUMBO_RECEIPT_REDIRECT_DETAIL_POC_CONTRACT_GREEN')
