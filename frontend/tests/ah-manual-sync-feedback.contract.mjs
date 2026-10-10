import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')

// A synchronizing request must have a visible, accessible in-progress state.
assert.match(source, /setAhSyncProgress\('AH-bonnen worden opgehaald en gecontroleerd/)
assert.match(source, /data-testid="ah-sync-progress"/)
assert.match(source, /aria-live="polite"/)
assert.match(source, /ahBusy \? 'AH-bonnen ophalen…' : 'Nu synchroniseren'/)

// A result must distinguish imported receipts, already-known receipts and errors.
assert.match(source, /receipts_processed/)
assert.match(source, /receipts_skipped_known/)
assert.match(source, /receipts_failed/)
assert.match(source, /entry\?\.stage === 'details'/)
assert.match(source, /entry\?\.stage === 'import'/)
assert.match(source, /failureDiagnosis/)
assert.doesNotMatch(source, /setAhSyncProgress\([^\n]*entry\.error\b/)
assert.match(source, /'AH-synchronisatie deels gelukt'/)
assert.match(source, /'AH-synchronisatie mislukt/)

console.log('AH_MANUAL_SYNC_FEEDBACK_CONTRACT_GREEN')
