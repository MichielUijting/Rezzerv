import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  hasPendingHistoryWork, historyCount, historicalStoreRows,
} from '../src/features/storeConnections/historicalImportStatusModel.js'

const summary = {
  auto_import_paused: false,
  providers: [
    { code: 'jumbo', kassa_receipts: 2, queue_pending: 3, queue_processing: 1 },
    { code: 'ah', kassa_receipts: 5, historical_receipts: 3, queue_pending: 0 },
  ],
}
assert.equal(hasPendingHistoryWork(summary), true)
assert.equal(hasPendingHistoryWork({ ...summary, auto_import_paused: true }), false)
assert.equal(hasPendingHistoryWork({ providers: [{ code: 'lidl', queue_pending: 0, queue_processing: 0 }] }), false)
assert.equal(hasPendingHistoryWork(null), false)
assert.equal(historyCount(null), '—')
assert.equal(historyCount(-1), '—')
assert.equal(historyCount('2000'), '—')
assert.equal(historyCount(1000), (1000).toLocaleString('nl-NL'))
assert.deepEqual(historicalStoreRows(summary).map(row => row.code), ['ah', 'lidl', 'jumbo'])
assert.equal(historicalStoreRows(summary)[0].historical_receipts, 3)
assert.deepEqual(historicalStoreRows(null), [])

const page = readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/features/storeConnections/HistoricalImportProgress.jsx', import.meta.url), 'utf8')
const route = readFileSync(new URL('../../backend/app/api/retailer_receipt_routes.py', import.meta.url), 'utf8')
const service = readFileSync(new URL('../../backend/app/services/retailer_history_progress.py', import.meta.url), 'utf8')
assert.match(page, /<HistoricalImportProgress/)
assert.match(page, /\/api\/receipts\/retailers\/history-progress/)
assert.match(page, /hasPendingHistoryWork\(historySummary\)/)
assert.match(page, /refreshHistoricalProgress\(\)/)
assert.match(panel, /historical-import-no-cutover/)
assert.match(panel, /historical-import-paused/)
assert.match(panel, /historical-import-refresh/)
assert.match(panel, /historical-import-evidence-/)
assert.match(panel, /\/api\/receipts\/retailers\/history-evidence/)
assert.match(panel, /Opgeslagen bonnen \(niet noodzakelijk in Kassa\)/)
assert.match(panel, /Waarvan nog in Kassa te behandelen/)
assert.match(service, /kassa_inbox_receipts/)
assert.doesNotMatch(panel, /In Kassa: /)
assert.match(route, /@router\.get\("\/history-evidence"\)/)
assert.match(service, /rt\.household_id = :household_id/)
assert.match(panel, /Bonnen uit de wachtrij zijn nog niet verwerkt in Kassa/)
assert.doesNotMatch(panel, /<progress/)
assert.match(route, /@router\.get\("\/history-progress"\)/)
assert.match(route, /household_id = _authorized_household_id\(authorization\)/)
assert.match(service, /rr\.household_id = :household_id/)
assert.match(service, /rt\.household_id = :household_id/)
assert.match(service, /retailer_import_queue/)
assert.match(service, /purchase_at_source/)
assert.match(service, /auto_import_paused/)
console.log('HISTORICAL_IMPORT_PROGRESS_CONTRACT_GREEN')
