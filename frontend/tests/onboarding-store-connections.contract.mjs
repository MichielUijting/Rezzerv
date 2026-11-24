import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  shouldOfferStoreConnectionOnboarding,
  filterOnboardingReceiptStores,
} from '../src/features/onboarding/onboardingStoreConnections.js'

function read(path) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const base = { onboarding_status: 'completed', can_manage: true, product_configuration: { receipt_processing_enabled: true } }
assert.equal(shouldOfferStoreConnectionOnboarding(base), true)
assert.equal(shouldOfferStoreConnectionOnboarding({ onboarding_status: 'completed', can_manage: true }), true, 'missing optional settings do not redirect to dashboard')
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, onboarding_status: 'in_progress' }), false)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, can_manage: false }), false)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, product_configuration: { receipt_processing_enabled: false } }), false)
assert.equal(shouldOfferStoreConnectionOnboarding(null), false)
assert.deepEqual(filterOnboardingReceiptStores([
  { providerCode: 'jumbo' }, { providerCode: 'ah' }, { providerCode: 'aldi' },
  { providerCode: 'lidl' }, { providerCode: 'picnic' }, { providerCode: 'plus' },
]).map(row => row.providerCode), ['jumbo', 'ah', 'lidl'])
assert.deepEqual(filterOnboardingReceiptStores(null), [])

const router = read('../src/app/router/AppRouter.jsx')
const onboarding = read('../src/features/onboarding/OnboardingPage.jsx')
const connections = read('../src/features/storeConnections/StoreConnectionsPage.jsx')
const oauth = read('../../backend/app/api/receipt_ah_oauth_proxy_routes.py')

assert.match(router, /shouldOfferStoreConnectionOnboarding\(completedOnboarding\)/)
assert.match(router, /path: '\/onboarding\/winkels', element: <ProtectedPermission permission="household_settings.manage"/)
assert.match(router, /<StoreConnectionsPage onboardingMode onFinish=/)
assert.match(onboarding, /onUseCaseSelected\?\.\(updated\)/)
assert.match(connections, /onboardingMode \? filterOnboardingReceiptStores\(overview\) : overview/)
assert.match(connections, /onboardingMode \? '\/onboarding\/winkels' : '\/instellingen\/winkelkoppelingen'/)
assert.match(connections, /data-testid="onboarding-stores-later"/)
assert.match(connections, /data-testid="onboarding-stores-continue"/)
assert.match(connections, /niet elke mobiele browser ondersteunt dit/)

// Returning from an Android external browser must not strand the AH connect button.
// A successful AH connection is confirmed only through the backend status call.
assert.match(connections, /const ahLoginNavigatingRef = useRef\(false\)/)
assert.match(connections, /ahLoginNavigatingRef\.current = true\s+window\.location\.assign\(data\.login_url\)/)
assert.match(connections, /window\.addEventListener\('pageshow', resumeAhLogin\)/)
assert.match(connections, /window\.addEventListener\('focus', resumeAhLogin\)/)
assert.match(connections, /document\.addEventListener\('visibilitychange', resumeAhLogin\)/)
assert.match(connections, /ahLoginNavigatingRef\.current = false\s+setAhBusy\(false\)\s+void loadAhStatus\(\)/)
assert.match(connections, /document\.visibilityState === 'hidden'/)
assert.match(oauth, /parsed\.path in \{"\/instellingen\/winkelkoppelingen", "\/onboarding\/winkels"\}/)

console.log('ONBOARDING_STORE_CONNECTIONS_CONTRACT_GREEN')
