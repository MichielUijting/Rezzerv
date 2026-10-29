import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')

// Transport ACK means durable receipt storage, not Kassa processing.
assert.match(source, /let lidlCounts = \{ queued: 0, failed: 0 \}/)
assert.match(source, /const result = await fetchJson\('\/api\/receipts\/retailers\/import-queue'/)
assert.match(source, /result\?\.received !== 1/)
assert.match(source, /result\?\.import_completed !== false/)
assert.match(source, /!result\.items\[0\]\?\.queue_id/)
assert.match(source, /lidlCounts\.queued \+= 1/)
assert.match(source, /lidlCounts\.failed \+= 1/)
assert.doesNotMatch(source, /importedCount \+= 1/)
assert.doesNotMatch(source, /Number\(data\.count \|\| importedCount/)

// Each browser session starts clean; unknown outcome is never acknowledged as received.
assert.match(source, /data\.type === 'inhuis:lidl-handshake'[\s\S]*?lidlCounts = \{ queued: 0, failed: 0 \}/)
assert.match(source, /Inhuis gaf geen herkenbaar importresultaat terug/)
assert.match(source, /lidlCounts\.queued === 0/)
assert.match(source, /Lidl-bonnen ontvangen/)
assert.match(source, /datum Laatst bijgewerkt wordt niet voortijdig doorgeschoven/)
assert.match(source, /Lidl-synchronisatie deels gelukt/)

// Scoped feedback cleanup mirrors AH, must not dismiss unrelated app notifications.
assert.match(source, /dismissFeedbackIfKey\('lidl-receipt-import'\)/)
assert.match(source, /lidlImportPageMountedRef\.current = false/)
assert.match(source, /if \(!lidlImportPageMountedRef\.current\) return/)
assert.match(source, /key: 'lidl-receipt-import'/)
assert.match(source, /dismissFeedbackIfKey\('ah-receipt-sync'\)/)

console.log('LIDL_IMPORT_FEEDBACK_CONTRACT_GREEN')
