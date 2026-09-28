import assert from 'node:assert/strict'
import fs from 'node:fs'
const page=fs.readFileSync(new URL('../src/features/receipts/ReceiptsPage.jsx', import.meta.url),'utf8')
const css=fs.readFileSync(new URL('../src/features/receipts/mobileReceipts.css', import.meta.url),'utf8')
assert.match(page,/useMobileAppViewport/)
assert.match(page,/data-testid="mobile-unpack-page"/)
assert.match(page,/rz-mobile-inventory-screen rz-mobile-unpack-screen/)
assert.match(page,/mobile-receipt-open-/)
assert.match(page,/StoreBatchDetailContent batchIdOverride=\{openedBatchId\} embedded/)
assert.match(page,/Terug naar overzicht/)
assert.match(css,/--size-app-bar-mobile/)
assert.match(css,/min-height:44px/)
console.log('mobile Uitpakken contract: OK')
