import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  shouldOfferStoreConnectionOnboarding,
  filterOnboardingReceiptStores,
  hasStoreOnboardingToResume,
  nextStoreForOnboarding, skipStoreForOnboarding,
} from '../src/features/onboarding/onboardingStoreConnections.js'
import { detectMobileRetailerEnvironment } from '../src/features/storeConnections/retailerMobileEnvironment.js'

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
assert.equal(nextStoreForOnboarding(['ah','jumbo'], { ah:'failed', jumbo:'failed' }), '',
  'failed stores cannot be retried automatically')
assert.equal(nextStoreForOnboarding(['ah','jumbo'], { ah:'failed', jumbo:'failed' }, '', true), 'ah',
  'explicit user action can retry failed stores')
assert.equal(hasStoreOnboardingToResume({ available:true, selected:['lidl'], results:{ lidl:'empty' } }), false)
assert.equal(nextStoreForOnboarding(['jumbo','lidl'], {jumbo:'empty'}, ''), 'lidl')

const router = read('../src/app/router/AppRouter.jsx')
const onboarding = read('../src/features/onboarding/OnboardingPage.jsx')
const connections = read('../src/features/storeConnections/StoreConnectionsPage.jsx')
const choice = read('../src/features/onboarding/StoreOnboardingSelection.jsx')
const style = read('../src/features/onboarding/storeOnboardingSelection.css')
const progressClient = read('../src/features/onboarding/onboardingStoreConnections.js')
const progressBackend = read('../../backend/app/services/store_onboarding_progress_service.py')
const routes = read('../../backend/app/api/household_onboarding_routes.py')
const defaults = read('../../backend/app/services/quick_start_onboarding_service.py')
const mobileHelp = read('../src/features/storeConnections/RetailerBookmarkletHelp.jsx')
const compactStyle = read('../src/features/storeConnections/receiptConnectionCompact.css')
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
assert.match(style, /var\(--color-ui-primary\)/)
assert.doesNotMatch(style, /#005f6a/i)
assert.match(read('../src/ui/tokens.css'), /--color-ui-primary:\s*#005F6A\s*;/i)
assert.match(style, /border-radius: 50%/)
assert.match(style, /vertical-align: middle/)
assert.match(connections, /<StoreOnboardingSelection/)
assert.doesNotMatch(connections, /<StoreConnectionWalkthrough/)
assert.match(connections, /startOnboardingStore/)
assert.match(connections, /if \(code === 'ah'\)/)
assert.match(connections, /void startAhLogin\(\)/)
assert.match(connections, /async function openLidlWithSavedPeriod/)
assert.match(connections, /stageJumboBatch\(/)
assert.match(connections, /markOnboardingStoreResult\('jumbo', run\.queued\.length \? 'success' : 'empty'/)
assert.match(connections, /markOnboardingStoreResult\('lidl', lidlCounts\.queued \? 'success' : 'empty'/)
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
assert.match(progressBackend, /FROM household_jumbo_import_runs/)
assert.match(progressBackend, /lidl_browser_import_run_v1/)
assert.match(progressBackend, /run\.get\("scan_complete"\) is not True/)
assert.match(routes, /run_id: str \| None = None/)
assert.match(connections, /lidl\/history\/complete/)
assert.match(connections, /jumbo\/history\/complete/)
assert.match(connections, /onboardingMode \|\| jumboPeriodValid/)
assert.match(connections, /onboardingMode \? undefined : JUMBO_ORDERS_URL/)
assert.match(connections, /onboardingMode=\{onboardingMode\}/)
assert.match(choice, /empty: 'Geen kassabonnen'/)
assert.match(progressBackend, /SETTING_KEY = "first_store_onboarding_v1"/)
assert.match(defaults, /seed_store_onboarding\(conn, household_id\)/)
assert.match(router, /onFinish=\{\(\) => navigate\('\/home'/)
assert.doesNotMatch(router, /wegwijs=1/)
assert.doesNotMatch(home, /FirstUseDashboardGuide|first-use-dashboard-guide|wegwijs/)
assert.doesNotMatch(compactStyle, /rz-first-use-action-hint/)
assert.match(compactStyle, /rz-onboarding-arrow-overlay/)
assert.match(mobileHelp, /Kopieer adres/)
assert.doesNotMatch(mobileHelp, /Stap [123] van 3/)
assert.match(mobileHelp, /document.title = universalBookmarklet/)
assert.match(connections, /copyRetailerBookmarklet\(universalBookmarklet\)/)
assert.match(connections, /jumboReturningRef\.current = true/)
assert.match(mobileHelp, /onOpenStore/)
assert.match(connections, /skipCurrentOnboardingStore/)
assert.match(connections, /async function finishGuidance\(\)/)
assert.match(connections, /const completed = storeOnboarding\.selected\.filter\(code =>/)
assert.match(connections, /await saveStoreOnboardingSelection\(completed\)/)
assert.match(connections, /saveStoreOnboardingSelection\(skipStoreForOnboarding/)
assert.match(connections, /detectMobileRetailerEnvironment/)
assert.match(connections, /onOpenStore=\{\(\) =>/)
assert.equal(detectMobileRetailerEnvironment({ userAgent: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36' }).browser, 'chrome')
assert.deepEqual(detectMobileRetailerEnvironment({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1' }), { device: 'iphone', browser: 'safari' })
assert.equal(detectMobileRetailerEnvironment({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/120.0.0 Mobile Safari/604.1' }).browser, 'other')
assert.equal(detectMobileRetailerEnvironment({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0' }).device, 'desktop')
assert.deepEqual(skipStoreForOnboarding(['ah','jumbo','lidl'], 'jumbo'), ['ah','lidl'])
assert.deepEqual(skipStoreForOnboarding(['lidl'], 'lidl'), [])
assert.equal(nextStoreForOnboarding(skipStoreForOnboarding(['jumbo','lidl'], 'jumbo'), {}, 'jumbo'), 'lidl')
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
assert.match(connections, /nextStoreForOnboarding\(confirmed\.selected, confirmed\.results, provider\)/)
assert.match(connections, /launchConfirmedOnboardingStore\(confirmed\)/)
assert.match(oauth, /only_household_id=flow\.household_id/)
assert.match(connections, /onboarding=true/)
assert.match(router, /function SettingsStoreConnectionsRoute/)
assert.match(router, /progress\.results\?\.ah !== 'success'/)
assert.match(connections, /event\.source !== expectedLidlWindowRef\.current/)
console.log('ONBOARDING_STORE_CONNECTIONS_CONTRACT_GREEN')

import { buildUniversalRetailerBookmarklet, mobileBookmarkletSetupKeys, hasMobileBookmarkletSetup, rememberMobileBookmarkletSetup, copyRetailerBookmarklet } from '../src/features/storeConnections/universalRetailerBookmarklet.js'
import { JUMBO_BOOKMARKLET_VERSION } from '../src/features/storeConnections/jumboReceiptPocBridge.js'
import { buildLidlWebBookmarklet } from '../src/features/storeConnections/lidlWebReceiptBridge.js'
import vm from 'node:vm'

const lidl = buildLidlWebBookmarklet('https://inhuis.example')
const universal = buildUniversalRetailerBookmarklet('https://inhuis.example', lidl)
assert.doesNotThrow(() => new Function(decodeURIComponent(universal.slice(11))))
assert.ok(!/[\r\n\t]/.test(universal))
const payload = decodeURIComponent(universal.slice('javascript:'.length))
assert.match(payload, /inhuis:jumbo-handshake/)
assert.match(payload, /inhuis:jumbo-script/)
assert.match(payload, /inhuis:lidl-handshake/)
assert.doesNotMatch(payload, /2026-10-01|2026-11-25|from_date|to_date/)
assert.equal(universal, buildUniversalRetailerBookmarklet('https://inhuis.example', lidl),
  'No date, path or browser session is baked into the permanent favorite')
assert.throws(() => buildUniversalRetailerBookmarklet('javascript:alert(1)', lidl), /Ongeldige/)
assert.throws(() => buildUniversalRetailerBookmarklet('https://evil.example', 'about:blank'), /Ongeldige/)

// Exact origin dispatch; never run either importer on an unrelated website.
const routing = decodeURIComponent(buildUniversalRetailerBookmarklet(
  'https://inhuis.example', 'javascript:(()=>{globalThis.selected="lidl"})()').slice(11))
for (const origin of ['https://example.com', 'https://www.jumbo.com.example.com', 'https://inhuis.example']) {
  const ctx = { location: { origin }, selected: '', alert: () => {} }
  vm.runInNewContext(routing, ctx)
  assert.equal(ctx.selected, '', origin + ' must not execute a retailer script')
}
const lidlCtx = { location: { origin: 'https://www.lidl.nl' }, selected: '', alert: () => {} }
vm.runInNewContext(routing, lidlCtx)
assert.equal(lidlCtx.selected, 'lidl')

// Jumbo must request the current period from the exact opener. A forged
// response or a missing opener may not execute an import.
{
  const alerts = []
  const ctx = { location: { origin: 'https://www.jumbo.com' }, alert: message => alerts.push(message) }
  vm.runInNewContext(routing, ctx)
  assert.match(alerts[0], /Open Jumbo eerst via/)
}
{
  let listener = null
  let executed = false
  let receiverRemoved = false
  const outbound = []
  const opener = { postMessage: (message, origin) => outbound.push({ message, origin }) }
  const ctx = {
    location: { origin: 'https://www.jumbo.com' },
    alert: () => { throw Error('Unexpected Jumbo error') },
    window: {
      opener,
      addEventListener: (_kind, fn) => { listener = fn },
      removeEventListener: () => { receiverRemoved = true },
      setTimeout: () => 1,
      clearTimeout: () => {},
    },
    selected: '',
  }
  ctx.window.window = ctx.window
  vm.runInNewContext(routing, ctx)
  assert.equal(outbound.length, 1)
  assert.equal(outbound[0].origin, 'https://inhuis.example')
  assert.equal(outbound[0].message.type, 'inhuis:jumbo-handshake')
  assert.equal(outbound[0].message.bookmarklet_version, JUMBO_BOOKMARKLET_VERSION)
  const response = {
    type: 'inhuis:jumbo-script',
    bookmarklet_version: JUMBO_BOOKMARKLET_VERSION,
    request_id: outbound[0].message.request_id,
    script: '(async()=>{globalThis.selected="jumbo"})()',
  }
  listener({ origin: 'https://evil.example', source: opener, data: response })
  listener({ origin: 'https://inhuis.example', source: {}, data: response })
  listener({ origin: 'https://inhuis.example', source: opener, data: { ...response, request_id: 'wrong' } })
  assert.equal(ctx.selected, '')
  listener({ origin: 'https://inhuis.example', source: opener, data: response })
  // new Function executes in the retailer's own context
  assert.equal(ctx.selected, 'jumbo')
  assert.equal(receiverRemoved, true)
  listener({ origin: 'https://inhuis.example', source: opener, data: response })
  assert.equal(ctx.selected, 'jumbo', 'Only one authorized execution per request')
}

// A single setup hint is shared, independent of dates and onboarding/settings.
const keys = mobileBookmarkletSetupKeys('/onboarding/winkels', '2026-10-01', '2026-11-25')
const changed = mobileBookmarkletSetupKeys('/instellingen/winkelkoppelingen', '2027-01-01', '2027-12-31')
assert.deepEqual(keys, changed)
assert.equal(keys.jumbo, keys.lidl)
const storage = new Map()
const mockStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) }
assert.equal(hasMobileBookmarkletSetup(keys.jumbo, mockStorage), false)
rememberMobileBookmarkletSetup(keys, mockStorage)
assert.equal(hasMobileBookmarkletSetup(changed.jumbo, mockStorage), true)
assert.equal(hasMobileBookmarkletSetup(changed.lidl, mockStorage), true)
let copied = ''
assert.equal(await copyRetailerBookmarklet(universal, { clipboard: { writeText: value => { copied = value; return Promise.resolve() } } }, {}), true)
assert.equal(copied, universal)
assert.equal(await copyRetailerBookmarklet(universal, { clipboard: { writeText: () => Promise.reject(new Error('blocked')) } }, {}), false)
assert.equal(await copyRetailerBookmarklet(universal, {}, {}), false)
assert.equal(detectMobileRetailerEnvironment({ userAgent: 'Mozilla/5.0 (Linux; Android 14; wv) Version/4.0 Chrome/130.0.0.0 Mobile Safari/537.36' }).browser, 'other')

// Selection changes are purely local; only confirmation persists once and then
// starts an AH/Jumbo/Lidl flow. A failed PUT leaves the pending state intact.
const selectHandler = connections.slice(
  connections.indexOf('function chooseOnboardingStore('),
  connections.indexOf('async function skipCurrentOnboardingStore('))
assert.match(selectHandler, /setPendingStoreSelection/)
assert.doesNotMatch(selectHandler, /saveStoreOnboardingSelection|fetchJson|setStoreOnboardingBusy|window\.location|navigate\(|setActiveProvider/)
const startHandler = connections.slice(
  connections.indexOf('async function startOnboardingStore('),
  connections.indexOf('function openJumboFromInhuis('))
assert.match(startHandler, /await saveStoreOnboardingSelection\(selected\)/)
assert.ok(startHandler.indexOf('await saveStoreOnboardingSelection(selected)') <
  startHandler.indexOf('launchConfirmedOnboardingStore(confirmed, preparedPromise)'))
assert.match(startHandler, /setPendingStoreSelection\(null\)/)
assert.match(connections, /currentJumboImportPeriod\(response\.dates\.jumbo\)/)
assert.match(connections, /event\.origin !== JUMBO_WEB_ORIGIN/)
assert.match(connections, /event\.source !== expectedJumboWindowRef\.current/)
assert.match(connections, /sourceWindow\.postMessage\(/)
assert.match(connections, /openJumboFromInhuis\(\)/)
assert.match(connections, /universalBookmarklet=\{universalBookmarklet\}/)
console.log('UNIVERSAL_MOBILE_BOOKMARKLET_CONTRACT_GREEN')
