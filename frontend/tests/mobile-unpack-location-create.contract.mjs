import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const page = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/features/receipts/mobileReceipts.css', import.meta.url), 'utf8')
assert.doesNotMatch(page, /data-testid="mobile-unpack-location-create-actions"/)
assert.match(page, /gridTemplateColumns: 'minmax\\(0, 1fr\\) minmax\\(0, 1fr\\)'/)
assert.match(page, /data-testid="receipt-location-create-space"/)
assert.match(page, /data-testid="receipt-location-create-sublocation"/)
assert.match(page, /setLocationCreateMode\\('sublocation'\\)/)
assert.match(page, /Voeg nu een sublocatie toe/)
assert.doesNotMatch(css, /rz-unpack-location-picker-columns \\{ grid-template-columns: minmax\\(0, 1fr\\) !important/)
console.log('MOBILE_UNPACK_LOCATION_CREATE_GREEN')
