/**
 * PR7: deterministic journey contract for a newly created household.
 *
 * This is not a simulated successful retailer login or a claim of full
 * provider-history coverage. Real-account acceptance is documented separately.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { shouldOfferStoreConnectionOnboarding, filterOnboardingReceiptStores } from '../src/features/onboarding/onboardingStoreConnections.js'
import { deriveReceiptConnectionOverview } from '../src/features/storeConnections/receiptConnectionOverviewModel.js'
import { hasPendingHistoryWork, historicalStoreRows, historyCount } from '../src/features/storeConnections/historicalImportStatusModel.js'

const household = {
  onboarding_status: 'completed',
  can_manage: true,
  product_configuration: { receipt_processing_enabled: true },
}
assert.equal(shouldOfferStoreConnectionOnboarding(household), true)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...household, product_configuration: undefined }), true)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...household, can_manage: false }), false)
assert.equal(shouldOfferStoreConnectionOnboarding({
  ...household, product_configuration: { receipt_processing_enabled: false },
}), false)

const today = new Date(2026, 10, 21)
const available = deriveReceiptConnectionOverview([], { connected: false }, {}, today)
const onboardingStores = filterOnboardingReceiptStores(available)
assert.deepEqual(onboardingStores.map(row => row.providerCode), ['ah', 'jumbo', 'lidl'])
assert.equal(onboardingStores[0].statusCode, 'not_connected')
assert.equal(onboardingStores[0].isAutomatic, false)
for (const row of onboardingStores.filter(item => item.providerCode !== 'ah')) {
  assert.equal(row.statusCode, 'browser')
  assert.equal(row.isAutomatic, false, 'A browser transfer is not a connected account')
}
assert.deepEqual(filterOnboardingReceiptStores(available).map(row => row.providerCode).sort(),
  ['ah', 'jumbo', 'lidl'].sort(), 'Unavailable stores are never onboarding actions')

const connected = filterOnboardingReceiptStores(
  deriveReceiptConnectionOverview([], { connected: true }, {}, today),
)
assert.equal(connected.find(row => row.providerCode === 'ah').statusCode, 'connected')
assert.equal(connected.find(row => row.providerCode === 'ah').isAutomatic, true)
assert.equal(connected.find(row => row.providerCode === 'lidl').statusCode, 'browser')
assert.equal(connected.find(row => row.providerCode === 'jumbo').statusCode, 'browser')

const persisted = {
  history_cutover_enabled: true,
  complete_retailer_history_known: false,
  auto_import_paused: false,
  providers: [
    { code: 'ah', kassa_receipts: 2, historical_receipts: 1, queue_pending: 0 },
    { code: 'lidl', kassa_receipts: 1, historical_receipts: 1, queue_pending: 3 },
    { code: 'jumbo', kassa_receipts: 0, historical_receipts: 0, queue_review_required: 1 },
  ],
}
const rows = historicalStoreRows(persisted)
assert.deepEqual(rows.map(row => row.code), ['ah', 'lidl', 'jumbo'])
assert.equal(rows[0].kassa_receipts, 2)
assert.equal(rows[0].historical_receipts, 1)
assert.equal(rows[1].queue_pending, 3)
assert.equal(rows[2].queue_review_required, 1)
assert.equal(hasPendingHistoryWork(persisted), true)
assert.equal(hasPendingHistoryWork({ ...persisted, auto_import_paused: true }), false,
  'A paused retailer import must not be polled as if it is running')
assert.equal(historyCount(undefined), '—')
assert.equal(historyCount(null), '—')
assert.equal(historyCount('999'), '—')
assert.equal(historyCount(0), '0')

// Source checks cover only the read-only explanation. They are not
// substitutes for PostgreSQL household isolation and idempotency gates.
const progressView = readFileSync(new URL('../src/features/storeConnections/HistoricalImportProgress.jsx', import.meta.url), 'utf8')
assert.match(progressView, /historical-import-paused/)
assert.match(progressView, /Bonnen uit de wachtrij zijn nog niet verwerkt in Kassa/)
assert.match(progressView, /geen onbevestigd totaal of percentage/)
assert.doesNotMatch(progressView, /<progress\b/)

console.log('ONBOARDING_PR7_JOURNEY_CONTRACT_GREEN')
