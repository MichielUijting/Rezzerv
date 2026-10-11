import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')

// The Lidl result must be classified from backend ingestion fields, not from HTTP success or browser count.
assert.match(source, /let lidlCounts = \{ new: 0, known: 0, refreshed: 0, failed: 0 \}/)
assert.match(source, /const result = await fetchJson\('\/api\/receipts\/retailers\/import'/)
assert.match(source, /result\?\.refreshed_existing_receipt/)
assert.match(source, /result\?\.duplicate === true/)
assert.match(source, /result\?\.duplicate === false && result\?\.raw_receipt_id/)
assert.match(source, /lidlCounts\.known \+= 1/)
assert.match(source, /lidlCounts\.new \+= 1/)
assert.match(source, /lidlCounts\.refreshed \+= 1/)
assert.match(source, /lidlCounts\.failed \+= 1/)
assert.doesNotMatch(source, /importedCount \+= 1/)
assert.doesNotMatch(source, /Number\(data\.count \|\| importedCount/)

// Each browser import session starts with clean counters; the UI must not claim an unknown outcome is new.
assert.match(source, /data\.type === 'inhuis:lidl-handshake'[\s\S]*?lidlCounts = \{ new: 0, known: 0, refreshed: 0, failed: 0 \}/)
assert.match(source, /Inhuis gaf geen herkenbaar importresultaat terug/)
assert.match(source, /al bekend, '[\s\S]*?lidlCounts\.refreshed/)
assert.match(source, /Lidl-synchronisatie afgerond/)
assert.match(source, /Lidl-synchronisatie deels gelukt/)

// Scoped feedback cleanup mirrors AH, must not dismiss unrelated app notifications.
assert.match(source, /dismissFeedbackIfKey\('lidl-receipt-import'\)/)
assert.match(source, /lidlImportPageMountedRef\.current = false/)
assert.match(source, /if \(!lidlImportPageMountedRef\.current\) return/)
assert.match(source, /key: 'lidl-receipt-import'/)
assert.match(source, /dismissFeedbackIfKey\('ah-receipt-sync'\)/)

console.log('LIDL_IMPORT_FEEDBACK_CONTRACT_GREEN')
