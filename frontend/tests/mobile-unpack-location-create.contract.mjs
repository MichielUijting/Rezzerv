import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const page = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/features/receipts/mobileReceipts.css', import.meta.url), 'utf8')
assert.match(page, /data-testid="mobile-unpack-location-create-actions"/)
assert.match(page, /setLocationCreateMode\('sublocation'\)/)
assert.match(page, /Voeg nu een sublocatie toe/)
assert.match(css, /\.rz-unpack-location-picker-columns/)
assert.match(css, /\.rz-mobile-unpack-create-actions/)
console.log('MOBILE_UNPACK_LOCATION_CREATE_GREEN')
