import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  shouldOfferStoreConnectionOnboarding,
  filterOnboardingReceiptStores,
  hasStoreOnboardingToResume,
  nextStoreForOnboarding,
} from '../src/features/onboarding/onboardingStoreConnections.js'

function read(path) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const base = { onboarding_status: 'completed', can_manage: true, product_configuration: { receipt_processing_enabled: true } }
assert.equal(shouldOfferStoreConnectionOnboarding(base), true)
assert.equal(shouldOfferStoreConnectionOnboarding({ onboarding_status: 'completed', can_manage: true }), true)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, onboarding_status: 'in_progress' }), false)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, can_manage: false }), false)
assert.equal(shouldOfferStoreConnectionOnboarding({ ...base, product_configuration: { receipt_processing_enabled: false } }), false)
assert.equal(shouldOfferStoreConnectionOnboarding(null), false)
assert.deepEqual(filterOnboardingReceiptStores([
  { providerCode: 'jumbo' }, { providerCode: 'ah' }, { providerCode: 'aldi' },
  { providerCode: 'lidl' }, { providerCode: 'picnic' }, { providerCode: 'plus' },
]).map(row => row.providerCode), ['jumbo', 'ah', 'lidl'])
assert.deepEqual(filterOnboardingReceiptStores(null), [])

// Only pending/failed deliberately selected stores trigger a re-login offer.
// Browser launch and merely viewing a store never count as a success.
assert.equal(hasStoreOnboardingToResume(null), false)
assert.equal(hasStoreOnboardingToResume({ available: false, selected: ['ah'], results: {} }), false)
assert.equal(hasStoreOnboardingToResume({ available: true, selected: [], results: {} }), false)
assert.equal(hasStoreOnboardingToResume({ available: true, selected: ['ah', 'lidl'], results: { ah: 'success', lidl: 'failed' } }), true)
assert.equal(hasStoreOnboardingToResume({ available: true, selected: ['ah'], results: { ah: 'success' } }), false)
assert.equal(hasStoreOnboardingToResume({ available: true, selected: ['jumbo'], results: {} }), true)


assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], {}, ''), 'ah')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], { ah: 'failed' }, 'ah'), 'jumbo')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], { ah: 'failed' }, ''), 'jumbo',
  'An AH OAuth redirect remount must not restart failed AH before untouched stores')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], { ah: 'failed', jumbo: 'failed' }, ''), 'lidl')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], { ah: 'failed', jumbo: 'success' }, 'jumbo'), 'lidl')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo', 'lidl'], { ah: 'success', jumbo: 'success' }, 'lidl'), 'lidl')
assert.equal(nextStoreForOnboarding(['ah', 'jumbo'], { ah: 'success', jumbo: 'success' }, 'ah'), '')
assert.equal(nextStoreForOnboarding(['lidl'], {}, ''), 'lidl')

const router = read('../src/app/router/AppRouter.jsx')
const onboarding = read('../src/features/onboarding/OnboardingPage.jsx')
const connections = read('../src/features/storeConnections/StoreConnectionsPage.jsx')
const choice = read('../src/features/onboarding/StoreOnboardingSelection.jsx')
const style = read('../src/features/onboarding/storeOnboardingSelection.css')
const progressClient = read('../src/features/onboarding/onboardingStoreConnections.js')
const progressBackend = read('../../backend/app/services/store_onboarding_progress_service.py')
const routes = read('../../backend/app/api/household_onboarding_routes.py')
const defaults = read('../../backend/app/services/quick_start_onboarding_service.py')
const dashboardGuide = read('../src/features/onboarding/FirstUseDashboardGuide.jsx')
const home = read('../src/features/home/HomePage.jsx')
const oauth = read('../../backend/app/api/receipt_ah_oauth_proxy_routes.py')

assert.match(router, /shouldOfferStoreConnectionOnboarding\(completedOnboarding\)/)
assert.match(router, /path: '\/onboarding\/winkels', element: <ProtectedPermission permission="household_settings.manage"/)
assert.match(router, /<StoreConnectionsPage onboardingMode onFinish=/)
assert.match(router, /hasStoreOnboardingToResume\(progress\)/)
assert.match(onboarding, /onUseCaseSelected\?\.\(updated\)/)
assert.match(connections, /onboardingMode \? filterOnboardingReceiptStores\(overview\) : overview/)
assert.match(connections, /onboardingMode \? '\/onboarding\/winkels' : '\/instellingen\/winkelkoppelingen'/)
assert.match(choice, /data-testid="onboarding-stores-later"/)
assert.match(choice, /data-testid="onboarding-stores-start"/)
assert.match(choice, /onSelect\(code, event\.target\.checked\)/)
assert.match(choice, /selected\.includes\(code\)/)
for (const label of ['Albert Heijn', 'Jumbo', 'Lidl']) assert.match(choice, new RegExp(label))
assert.match(choice, /aria-live="polite"/)
assert.match(choice, /data-result=\{result \|\| 'neutral'\}/)
assert.match(style, /tr\[data-result="success"\]/)
assert.match(style, /tr\[data-result="failed"\]/)
assert.match(style, /--color-ui-primary, #005F6A/)
assert.match(style, /border-radius: 50%/)
assert.match(style, /vertical-align: middle/)
assert.match(connections, /<StoreOnboardingSelection/)
assert.doesNotMatch(connections, /<StoreConnectionWalkthrough/)
assert.match(connections, /startOnboardingStore/)
assert.match(connections, /if \(code === 'ah'\)/)
assert.match(connections, /void startAhLogin\(\)/)
assert.match(connections, /async function openLidlWithSavedPeriod/)
assert.match(connections, /stageJumboBatch\(/)
assert.match(connections, /markOnboardingStoreResult\('jumbo', 'success', queued\[0\]\.queue_id\)/)
assert.match(connections, /markOnboardingStoreResult\('lidl', 'success', lidlOnboardingQueueIdRef\.current\)/)
assert.match(connections, /if \(confirmation\?\.connected === true\)/)
assert.match(progressClient, /credentials: 'include'/)
assert.match(progressClient, /'\/api\/onboarding\/stores\/selection'/)
assert.match(progressClient, /'\/api\/onboarding\/stores\/result'/)
assert.match(routes, /_regular_household_context\(conn, request\)/)
assert.match(routes, /_require_manage_onboarding\(conn, context\)/)
assert.match(routes, /@router\.get\("\/api\/onboarding\/stores"\)/)
assert.match(routes, /@router\.put\("\/api\/onboarding\/stores\/selection"\)/)
assert.match(routes, /@router\.post\("\/api\/onboarding\/stores\/result"\)/)
assert.match(progressBackend, /WHERE household_id = :household_id AND provider = 'ah'/)
assert.match(progressBackend, /FROM retailer_import_queue/)
assert.match(progressBackend, /AND id = :queue_id/)
assert.match(progressBackend, /SETTING_KEY = "first_store_onboarding_v1"/)
assert.match(defaults, /seed_store_onboarding\(conn, household_id\)/)
assert.match(router, /navigate\('\/home\?wegwijs=1'/)
assert.match(home, /<FirstUseDashboardGuide/)
assert.match(dashboardGuide, /rz-first-use-action-hint/)
assert.doesNotMatch(dashboardGuide, /rgba\(0, 0, 0/)
assert.match(oauth, /parsed\.path in \{"\/instellingen\/winkelkoppelingen", "\/onboarding\/winkels"\}/)

// Android return and browser OAuth never substitute navigation for proof.
assert.match(connections, /const ahLoginNavigatingRef = useRef\(false\)/)
assert.match(connections, /ahLoginNavigatingRef\.current = true\s+window\.location\.assign\(data\.login_url\)/)
assert.match(connections, /window\.addEventListener\('pageshow', resumeAhLogin\)/)
assert.match(connections, /window\.addEventListener\('focus', resumeAhLogin\)/)
assert.match(connections, /document\.addEventListener\('visibilitychange', resumeAhLogin\)/)
assert.match(connections, /ahLoginNavigatingRef\.current = false\s+setAhBusy\(false\)/)
assert.match(connections, /document\.visibilityState === 'hidden'/)
assert.match(connections, /const confirmation = await loadAhStatus\(\)/)
assert.match(connections, /ahReturnOutcomeRef\.current = fromUrl/)
assert.match(connections, /ahReturnOutcomeRef\.current = null/)
assert.match(connections, /De AH-login is niet voltooid of verlopen/)
assert.doesNotMatch(connections, /if \(ahResult === 'connected'\) \{\s*setActiveProvider\('ah'\)/)
console.log('ONBOARDING_STORE_CONNECTIONS_CONTRACT_GREEN')
