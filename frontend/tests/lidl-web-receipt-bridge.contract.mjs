import assert from 'node:assert/strict'
import {
  LIDL_HISTORY_URL,
  LIDL_WEB_ORIGIN,
  buildLidlWebBookmarklet,
  buildLidlWebPageScript,
} from '../src/features/storeConnections/lidlWebReceiptBridge.js'

assert.equal(LIDL_WEB_ORIGIN, 'https://www.lidl.nl')
assert.match(LIDL_HISTORY_URL, /\/mre\/purchase-history/)
assert.match(LIDL_HISTORY_URL, /client_id=NetherlandsEcommerceClient/)

const bookmarklet = buildLidlWebBookmarklet('http://localhost:5174')
assert.match(bookmarklet, /^javascript:/)
assert.match(bookmarklet, /lidlImport=1/)
assert.match(bookmarklet, /http:\/\/localhost:5174/)

const script = buildLidlWebPageScript('http://localhost:5174')
assert.match(script, /\/mre\/purchase-history/)
assert.match(script, /\/mre\/purchase-detail/)
assert.match(script, /NetherlandsEcommerceClient/)
assert.match(script, /data-art-description/)
assert.match(script, /inhuis:lidl-receipt/)
assert.match(script, /inhuis:lidl-complete/)
assert.doesNotMatch(script, /document\.cookie/)
assert.doesNotMatch(script, /localStorage/)
assert.doesNotMatch(script, /sessionStorage/)
assert.doesNotMatch(script, /Password|password/)

console.log('LIDL_WEB_RECEIPT_BRIDGE_CONTRACT_GREEN')
