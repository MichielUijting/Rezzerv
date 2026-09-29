import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const picker = page.slice(page.indexOf('data-testid="receipt-location-use-standard"'), page.indexOf('{barcodeSaveConfirm ? ('))
assert.ok(picker, 'Locatiekiezer moet aanwezig zijn')
assert.doesNotMatch(picker, /Beheer locaties/)
assert.match(picker, /onClick=\{closeLocationPicker\}>\s*Overnemen/)
assert.match(page, /data-testid="receipt-location-create-space"/)
assert.match(page, /data-testid="receipt-location-create-sublocation"/)
console.log('MOBILE_UNPACK_PICKER_ACTIONS_GREEN')
