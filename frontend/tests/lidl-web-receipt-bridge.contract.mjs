import assert from 'node:assert/strict'
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

console.log('LIDL_WEB_RECEIPT_BRIDGE_CONTRACT_GREEN')
