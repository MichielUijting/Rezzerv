import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const picker = page.slice(page.indexOf('data-testid="receipt-location-use-standard"'), page.indexOf('{barcodeSaveConfirm ? ('))
assert.ok(picker.startsWith('data-testid='), 'Locatiekiezer moet aanwezig zijn')
assert.doesNotMatch(picker, /Beheer locaties/)
assert.match(picker, /onClick=\{closeLocationPicker\}>\s*Overnemen/)
assert.match(page, /data-testid="receipt-location-create-space"/)
assert.match(page, /data-testid="receipt-location-create-sublocation"/)
console.log('MOBILE_UNPACK_PICKER_ACTIONS_GREEN')

// De gedeelde locatiekiezer werkt in mobiel en desktop hetzelfde.
assert.match(page, /placeholder="Zoek locatie of sublocatie\\.\\.\\."/)
assert.match(page, /sublocationOptionsForSpace\\(locationOptions, location\\.space_id \\|\\| location\\.id\\)/)
assert.match(page, /visibleSublocations\\.map/)
assert.match(page, /rz-unpack-location-picker-footer/)
assert.match(page, /repeat\\(3, minmax\\(0, 1fr\\)\\)/)
