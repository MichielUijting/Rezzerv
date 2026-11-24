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
const storeGuide = read('../src/features/onboarding/StoreConnectionWalkthrough.jsx')
const compactCss = read('../src/features/storeConnections/receiptConnectionCompact.css')
const dashboardGuide = read('../src/features/onboarding/FirstUseDashboardGuide.jsx')
const home = read('../src/features/home/HomePage.jsx')
const oauth = read('../../backend/app/api/receipt_ah_oauth_proxy_routes.py')

assert.match(router, /shouldOfferStoreConnectionOnboarding\(completedOnboarding\)/)
assert.match(router, /path: '\/onboarding\/winkels', element: <ProtectedPermission permission="household_settings.manage"/)
assert.match(router, /<StoreConnectionsPage onboardingMode onFinish=/)
assert.match(onboarding, /onUseCaseSelected\?\.\(updated\)/)
assert.match(connections, /onboardingMode \? filterOnboardingReceiptStores\(overview\) : overview/)
assert.match(connections, /onboardingMode \? '\/onboarding\/winkels' : '\/instellingen\/winkelkoppelingen'/)
assert.match(connections, /data-testid="onboarding-stores-later"/)
assert.match(connections, /data-testid="onboarding-stores-continue"/)
// 24 November PO revision: guidance is anchored orange arrows, not a big card.
assert.match(storeGuide, /code: 'ah', name: 'Albert Heijn'/)
assert.match(storeGuide, /code: 'jumbo', name: 'Jumbo'/)
assert.match(storeGuide, /code: 'lidl', name: 'Lidl'/)
assert.ok(storeGuide.indexOf("code: 'ah'") < storeGuide.indexOf("code: 'jumbo'"))
assert.ok(storeGuide.indexOf("code: 'jumbo'") < storeGuide.indexOf("code: 'lidl'"))
assert.match(storeGuide, /receipt-connection-action-/)
assert.match(storeGuide, /getBoundingClientRect\(\)/)
assert.match(storeGuide, /scrollIntoView\(/)
assert.match(storeGuide, /window\.addEventListener\('click', advance, true\)/)
assert.match(storeGuide, /window\.localStorage\.setItem/)
assert.match(storeGuide, /step !== STORES\.length/)
assert.match(storeGuide, /finishedRef\.current = true/)
assert.match(storeGuide, /const GUIDE_FINISHED = STORES\.length \+ 1/)
assert.match(storeGuide, /completeStoreConnectionGuidance\(householdId\)/)
assert.match(connections, /onClick=\{finishGuidance\}/)
assert.match(storeGuide, /rz-onboarding-arrow-overlay/)
assert.match(connections, /<StoreConnectionWalkthrough/)
assert.doesNotMatch(connections, /data-testid="onboarding-stores-step"/)
assert.match(connections, /data-testid="store-connections-help"/)
assert.match(connections, /data-testid="store-connections-guide-dashboard"/)
assert.match(connections, /<span>Status<\/span>\s*<span>Laatst bijgewerkt<\/span>/)
const columns = connections.slice(connections.indexOf('const receiptConnectionColumns'), connections.indexOf('const storeConnectionColumns'))
assert.ok(columns.indexOf("key: 'action'") < columns.indexOf("key: 'lastSyncLabel'"), 'status before last updated in DataTable')
assert.match(compactCss, /#D97706/)
assert.match(compactCss, /pointer-events: none/)
assert.match(compactCss, /rz-receipt-connection-guide-target/)
assert.match(compactCss, /padding: 9px 8px !important/)
assert.match(router, /navigate\('\/home\?wegwijs=1'/)
assert.match(home, /<FirstUseDashboardGuide/)
assert.match(dashboardGuide, /rz-first-use-action-hint/)
assert.match(dashboardGuide, /window\.addEventListener\('click', dismiss, true\)/)
assert.match(dashboardGuide, /Via Meer vind je de overige functies/)
assert.doesNotMatch(dashboardGuide, /rgba\(0, 0, 0/)


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
