import { Capacitor } from '@capacitor/core'
import { InAppBrowser } from '@capgo/capacitor-inappbrowser'
import {
  stores, isHistoryUrl, probeScript, acceptEvidence, canBeginLidlImport, jumboStateScript,
  acceptJumboState, jumboTransition, jumboOpenLoginScript, acceptJumboAction,
} from './probe.mjs'
import {
  secureInhuisUrl, validShellMessage, jumboNativeEventAllowed, lidlNativeEventAllowed,
  validNativeAhLaunch, nativeAhReturn,
} from './app-contract.mjs'

const form = document.getElementById('connect')
const input = document.getElementById('inhuis-url')
const status = document.getElementById('status')
const button = form.querySelector('button')
const store = stores.jumbo
const lidlStore = stores.lidl
let inhuis = null
let jumbo = null
let lidl = null
let ah = null
let opening = false
const listeners = []

function say(message) { status.textContent = message }
function validJumboLocation(url) {
  try {
    const target = new URL(url)
    return target.origin === store.origin && !target.username && !target.password
  } catch { return false }
}
function afterClose(run) {
  if (jumbo !== run) return
  if (run.handshakeSent && !run.finished) {
    void transmitToInhuis(run, {
      type: 'inhuis:jumbo-error', request_id: run.requestId, version: 14,
      source_origin: store.origin,
      error: 'Jumbo is gesloten voordat de import is afgerond.',
    }).catch(() => {})
  }
  clearInterval(run.interval)
  jumbo = null
  say('Terug in Inhuis. Een bon is pas verwerkt na bevestiging in Inhuis.')
}
async function closeJumbo() {
  const run = jumbo
  if (!run) return
  clearInterval(run.interval)
  jumbo = null
  if (run.id) {
    try { await InAppBrowser.close({ id: run.id }) } catch { /* Already closed. */ }
  }
}
async function transmitToInhuis(run, data) {
  if (run !== jumbo || !inhuis?.id || inhuis.origin !== secureInhuisUrl(inhuis.origin)) return
  // Never embed untrusted text in executable JS. Serialize a JSON value, with
  // a bounded size and an exact origin/channel check in the destination.
  const payload = {
    kind: 'inhuis-native-jumbo-relay',
    channel: inhuis.channel, nonce: run.transportNonce, data,
  }
  const json = JSON.stringify(payload)
  if (json.length > 950000) throw Error('Jumbo batch exceeds native message limit')
  const code = `(() => {
    if (window.top !== window || location.origin !== ${JSON.stringify(inhuis.origin)} ||
        window.__inhuisNativeShell?.channel !== ${JSON.stringify(inhuis.channel)}) return;
    window.dispatchEvent(new CustomEvent('inhuis-native-jumbo-event', { detail: ${json} }));
  })()`
  await InAppBrowser.executeScript({ id: inhuis.id, code })
}
async function advertiseInhuisBridge() {
  if (!inhuis?.id) return
  const { id, origin, channel } = inhuis
  const code = `(() => {
    if (window.top !== window || location.origin !== ${JSON.stringify(origin)} ||
        typeof window.mobileApp?.postMessage !== 'function') return;
    window.__inhuisNativeShell = Object.freeze({
      version: 1, channel: ${JSON.stringify(channel)},
    });
    window.dispatchEvent(new Event('inhuis-native-shell-ready'));
  })()`
  try { await InAppBrowser.executeScript({ id, code }) }
  catch { say('Inhuis kon de native browserkoppeling nog niet voorbereiden. Open het scherm opnieuw.') }
}
async function inspect(run) {
  if (run !== jumbo || !run.id || run.inspecting || !run.jumboOrigin || run.failed ||
      run.scriptInjected || run.handshakeSent && run.apiStarted) return
  run.inspecting = true
  try {
    await InAppBrowser.executeScript({
      id: run.id,
      code: jumboStateScript(run.nonce) + ';' + probeScript(store, run.nonce),
    })
  } catch { /* Failed page loads and OAuth redirects can be retried safely. */ }
  finally { run.inspecting = false }
}
async function installOpenerAndScript(run, script) {
  if (jumbo !== run || run.scriptInjected || run.failed || !run.jumboOrigin ||
      !run.historyReached || typeof script !== 'string' ||
      script.length < 5000 || script.length > 200000 ||
      !script.startsWith('(async()=>{') ||
      !script.includes('const NATIVE=true;') ||
      !script.includes('const V=14;') ||
      !script.includes('const O=' + JSON.stringify(inhuis.origin) + ';') ||
      !script.includes('const Q=' + JSON.stringify(run.requestId) + ';') ||
      !script.includes('GetOnlineOrdersAndStoreReceipts')) throw Error('Ongeldig of niet-gebonden Jumbo-script')
  const guard = JSON.stringify({
    jumbo: store.origin, inhuis: inhuis.origin, nonce: run.nonce,
  })
  const shim = `(() => {
    const c = ${guard};
    if (window.top !== window || location.origin !== c.jumbo ||
        location.pathname !== '/bestellingen' ||
        typeof window.mobileApp?.postMessage !== 'function') return;
    window.__inhuisNativeJumboOpener = Object.freeze({
      postMessage(data, origin) {
        if (origin !== c.inhuis || !data || typeof data !== 'object') return;
        window.mobileApp.postMessage({
          detail: { kind: 'inhuis-native-jumbo-data', nonce: c.nonce, data },
        });
      },
      focus() {},
    });
  })()`
  // The provider page is never navigated to guessed routes. The link-click
  // and the authorized /bestellingen origin are proven before injection.
  // One execution avoids a race between installing the opener and starting the runner.
  run.scriptInjected = true
  armLidlWatchdog(run, 'Lidl-importscript geeft geen voortgang terug. Probeer opnieuw.')
  await InAppBrowser.executeScript({ id: run.id, code: shim + ';\n' + script })
}
// Persist only a salted-free, nonreversible context digest, never an Inhuis
// password/session cookie or a Jumbo token. All browsing data must be cleared
// before a different Inhuis identity can reuse persistent Jumbo login state.
const JUMBO_OWNER_KEY = 'inhuis-jumbo-owner-sha256'
async function safeJumboOwner(binding) {
  if (!binding || !/^[^\\s]{1,128}$/.test(String(binding.userId || '')) ||
      !/^[^\\s]{1,128}$/.test(String(binding.householdId || '')) ||
      String(binding.householdId) === '0') return false
  const bytes = new TextEncoder().encode(JSON.stringify([
    inhuis?.origin, binding.userId, binding.householdId,
  ]))
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('')
  const old = localStorage.getItem(JUMBO_OWNER_KEY)
  if (old && old !== digest) {
    // CookieManager/WebStorage are process-wide on Android. Selectively
    // clearing one WebView cannot prove an old Jumbo OAuth session is gone.
    // Clear and refuse this run; the user signs into Inhuis afresh.
    await InAppBrowser.clearAllBrowsingData()
    localStorage.setItem(JUMBO_OWNER_KEY, digest)
    say('Andere Inhuis-gebruiker of ander huishouden. Bewaarde winkelsessies zijn gewist. Meld je opnieuw aan bij Inhuis en probeer Jumbo opnieuw.')
    return false
  }
  localStorage.setItem(JUMBO_OWNER_KEY, digest)
  return true
}

// Open AH only through the trusted Tailscale HTTPS listener :8443.
// This window never receives Inhuis bridge or household credentials.
async function finishAh(run, outcome) {
  if (ah !== run) return
  ah = null
  if (run.id) {
    try { await InAppBrowser.close({ id: run.id }) } catch { /* Already closed. */ }
  }
  if (!inhuis?.id) return
  const target = inhuis.origin + (outcome?.path || '/onboarding/winkels') +
    '?ah=' + (outcome?.result || 'error')
  const code = '(() => { if (window.top !== window || location.origin !== ' +
    JSON.stringify(inhuis.origin) + ') return; location.assign(' +
    JSON.stringify(target) + '); })()'
  try { await InAppBrowser.executeScript({ id: inhuis.id, code }) }
  catch { say('AH is gesloten. Open Winkelkoppelingen opnieuw om de echte status te controleren.') }
}

async function handleInhuisAhStart(d) {
  if (ah || jumbo || lidl || opening || !validNativeAhLaunch(d.url, inhuis?.origin)) return
  opening = true
  try {
    if (!await safeJumboOwner(d.binding)) return
    const run = { id: null }
    ah = run
    const view = await InAppBrowser.openWebView({
      url: d.url, javascriptBridgeOrigins: [],
      allowScreenshotsFromWebPage: false, preventDeeplink: true,
      persistWebViewData: true, visibleTitle: true, openBlankTargetInWebView: true,
    })
    if (ah !== run || typeof view?.id !== 'string' || !view.id) throw Error('AH WebView ontbreekt')
    run.id = view.id
  } catch {
    if (ah) await finishAh(ah, { path: '/onboarding/winkels', result: 'error' })
    else say('AH kon niet worden geopend. Geen accountstatus gewijzigd.')
  } finally { opening = false }
}

async function handleInhuisMessage(event) {
  const runShell = inhuis
  const d = event?.detail
  if (!runShell || !validShellMessage(event, runShell.id, runShell.channel, runShell.origin, d)) return
  if (d.kind === 'inhuis-native-ah-start') {
    await handleInhuisAhStart(d)
    return
  }
  if (d.kind.startsWith('inhuis-native-lidl-')) {
    await handleInhuisLidlMessage(d)
    return
  }
  if (d.kind === 'inhuis-native-jumbo-start') {
    if (jumbo || opening) return
    opening = true
    try {
      if (!await safeJumboOwner(d.binding)) return
    } catch {
      say('Jumbo is voor dit Inhuis-account geblokkeerd: de oude winkelsessie kon niet veilig worden gewist.')
      return
    } finally { opening = false }
    opening = true
    const run = {
      store, phase: 'combined', manual: false, id: null, url: null,
      nonce: crypto.randomUUID(), transportNonce: d.nonce,
      requestId: crypto.randomUUID(), jumboOrigin: false, historyReached: false,
      handshakeSent: false, scriptInjected: false, inspecting: false,
      navigationAttempted: false, failed: false, blocked: false,
    }
    jumbo = run
    say('Jumbo openen. Je meldt je alleen op de officiële Jumbo-website aan.')
    try {
      const browser = await InAppBrowser.openWebView({
        url: store.startUrl, javascriptBridgeOrigins: [store.origin],
        allowScreenshotsFromWebPage: false, preventDeeplink: true,
        persistWebViewData: true, visibleTitle: true, openBlankTargetInWebView: true,
      })
      if (jumbo !== run || typeof browser?.id !== 'string' || !browser.id) {
        throw Error('Jumbo WebView did not open')
      }
      run.id = browser.id
      run.jumboOrigin = true
      run.interval = setInterval(() => void inspect(run), 1500)
      void inspect(run)
    } catch {
      await closeJumbo()
      say('Jumbo kon niet worden geopend. Probeer het opnieuw; Inhuis heeft geen bonnen geïmporteerd.')
    } finally { opening = false }
    return
  }
  const run = jumbo
  if (!run || run.transportNonce !== d.nonce) return
  if (d.kind === 'inhuis-native-jumbo-cancel') {
    run.finished = true
    await closeJumbo()
    return
  }
  if (d.kind !== 'inhuis-native-jumbo-command' || !d.data) return
  const cmd = d.data
  if (cmd.type === 'inhuis:jumbo-script') {
    if (!run.handshakeSent || cmd.bookmarklet_version !== 14 ||
        cmd.request_id !== run.requestId) return
    try { await installOpenerAndScript(run, cmd.script) }
    catch {
      run.failed = true
      say('Het ophalen van Jumbo-bonnen is veilig gestopt. Open Jumbo opnieuw vanuit Inhuis.')
      await closeJumbo()
    }
    return
  }
  if (cmd.type === 'inhuis:jumbo-ack') {
    if (!run.scriptInjected || cmd.request_id !== run.requestId ||
        cmd.version !== 14 || !Number.isInteger(cmd.index) ||
        typeof cmd.ok !== 'boolean') return
    const data = JSON.stringify(cmd)
    const code = `(() => {
      if (window.top !== window || location.origin !== ${JSON.stringify(store.origin)} ||
          location.pathname !== '/bestellingen') return;
      window.dispatchEvent(new CustomEvent('inhuis-native-jumbo-ack', { detail: ${data} }));
    })()`
    try { await InAppBrowser.executeScript({ id: run.id, code }) } catch { /* Pending batch safely times out. */ }
  }
}
async function handleJumboMessage(event) {
  const run = jumbo
  if (!run || !run.id || event?.id !== run.id) return
  const d = event.detail
  if (jumboNativeEventAllowed(event, run, d)) {
    if (JSON.stringify(d.data).length > 950000) return
    try { await transmitToInhuis(run, d.data) }
    catch { say('Een Jumbo-deelbatch kon niet worden bevestigd. De periode blijft hervatbaar.') }
    return
  }
  const state = acceptJumboState(event, run)
  if (state) {
    const action = jumboTransition(run, state)
    if (action === 'login' || action === 'receipts') {
      try { await InAppBrowser.executeScript({
        id: run.id, code: jumboOpenLoginScript(run.nonce, action),
      }) } catch { /* User can retry login from the provider page. */ }
    }
    return
  }
  const selected = acceptJumboAction(event, run)
  if (selected) {
    if (selected.action === 'receipts') {
      run.navigationAccepted = selected.acted
      if (!selected.acted && (run.retries || 0) < 5) {
        run.retries = (run.retries || 0) + 1
        run.navigationAttempted = false
      }
    }
    return
  }
  const evidence = acceptEvidence(event, run)
  if (!evidence || d?.route !== 'bestellingen' || run.handshakeSent ||
      !run.jumboOrigin || run.blocked) return
  run.historyReached = true
  run.handshakeSent = true
  try {
    await transmitToInhuis(run, {
      type: 'inhuis:jumbo-handshake',
      bookmarklet_version: 14, request_id: run.requestId,
    })
  } catch {
    run.failed = true
    say('Verbinding met Inhuis onderbroken; geen import gestart. Probeer opnieuw.')
    await closeJumbo()
  }
}

function validLidlLocation(url) {
  try {
    const parsed = new URL(url)
    return parsed.origin === lidlStore.origin && !parsed.username && !parsed.password
  } catch { return false }
}

function afterLidlClose(run) {
  if (lidl !== run) return
  clearTimeout(run.watchdog)
  if (!run.finished && run.handshakeSent) {
    void transmitLidlToInhuis(run, {
      type: 'inhuis:lidl-error',
      message: 'Lidl is gesloten voordat de bonimport door Inhuis was bevestigd.',
      request_id: run.requestId,
    }).catch(() => {})
  }
  clearInterval(run.interval)
  lidl = null
}

async function closeLidl() {
  const run = lidl
  if (!run) return
  clearInterval(run.interval)
  clearTimeout(run.watchdog)
  lidl = null
  if (run.id) {
    try { await InAppBrowser.close({ id: run.id }) } catch { /* Already closed. */ }
  }
}

async function transmitLidlToInhuis(run, data) {
  if (run !== lidl || !inhuis?.id || inhuis.origin !== secureInhuisUrl(inhuis.origin)) return
  const payload = {
    kind: 'inhuis-native-lidl-relay', channel: inhuis.channel,
    nonce: run.transportNonce, data,
  }
  const json = JSON.stringify(payload)
  if (json.length > 950000) throw Error('Lidl batch exceeds native message limit')
  const code = `(() => {
    if (window.top !== window || location.origin !== ${JSON.stringify(inhuis.origin)} ||
        window.__inhuisNativeShell?.channel !== ${JSON.stringify(inhuis.channel)}) return;
    window.dispatchEvent(new CustomEvent('inhuis-native-lidl-event', { detail: ${json} }));
  })()`
  await InAppBrowser.executeScript({ id: inhuis.id, code })
}

function armLidlWatchdog(run, message) {
  clearTimeout(run.watchdog)
  run.watchdog = setTimeout(async () => {
    if (lidl !== run || run.finished) return
    run.failed = true
    await transmitLidlToInhuis(run, {
      type: 'inhuis:lidl-error', request_id: run.requestId, message,
    }).catch(() => {})
    await closeLidl()
  }, 90000)
}

async function inspectLidl(run) {
  if (run !== lidl || !run.id || run.inspecting || run.failed ||
      run.handshakeSent || !run.lidlOrigin || !run.url) return
  run.inspecting = true
  try {
    await InAppBrowser.executeScript({ id: run.id, code: probeScript(lidlStore, run.nonce) })
  } catch { /* Login redirects and page loads can retry safely. */ }
  finally { run.inspecting = false }
}

async function installLidlScript(run, script) {
  if (run !== lidl || !run.id || !run.lidlOrigin || !run.historyReached ||
      run.failed || run.scriptInjected || !run.handshakeSent ||
      typeof script !== 'string' || script.length > 200000 ||
      !script.startsWith('/* INHUIS_LIDL_NATIVE_V2 */(') ||
      !script.includes('"native_request_id":' + JSON.stringify(run.requestId)) ||
      !script.includes(JSON.stringify(inhuis.origin)) ||
      !script.includes('/mre/purchase-history')) {
    throw Error('Ongeldig of niet-gebonden Lidl-importscript')
  }
  const config = JSON.stringify({
    origin: lidlStore.origin, inhuis: inhuis.origin,
    nonce: run.nonce, requestId: run.requestId,
  })
  const shim = `(() => {
    const c = ${config};
    if (window.top !== window || location.origin !== c.origin ||
        location.pathname !== '/mre/purchase-history' ||
        typeof window.mobileApp?.postMessage !== 'function') return;
    window.__inhuisNativeLidlOpener = Object.freeze({
      postMessage(data, origin) {
        if (origin !== c.inhuis || !data || typeof data !== 'object' ||
            !['inhuis:lidl-progress', 'inhuis:lidl-receipt', 'inhuis:lidl-complete',
              'inhuis:lidl-error'].includes(data.type)) return;
        window.mobileApp.postMessage({ detail: {
          kind: 'inhuis-native-lidl-data', nonce: c.nonce,
          data: { ...data, request_id: c.requestId },
        } });
      },
      focus() {},
    });
  })()`
  await InAppBrowser.executeScript({ id: run.id, code: shim })
  run.scriptInjected = true
  await InAppBrowser.executeScript({ id: run.id, code: script })
}

async function handleInhuisLidlMessage(d) {
  if (d.kind === 'inhuis-native-lidl-start') {
    if (lidl || jumbo || ah || opening) return
    opening = true
    try {
      if (!await safeJumboOwner(d.binding)) return
    } catch {
      say('Lidl is geblokkeerd: de oude winkelsessie kon niet veilig worden gewist.')
      return
    } finally { opening = false }
    opening = true
    const run = {
      store: lidlStore, id: null, url: null,
      nonce: crypto.randomUUID(), transportNonce: d.nonce,
      requestId: crypto.randomUUID(), lidlOrigin: false,
      historyReached: false, handshakeSent: false, scriptInjected: false,
      inspecting: false, failed: false, finished: false,
    }
    lidl = run
    say('Lidl openen. Je meldt je uitsluitend bij de officiële Lidl-website aan.')
    try {
      const browser = await InAppBrowser.openWebView({
        url: lidlStore.url, javascriptBridgeOrigins: [lidlStore.origin],
        allowScreenshotsFromWebPage: false, preventDeeplink: true,
        persistWebViewData: true, visibleTitle: true, openBlankTargetInWebView: true,
      })
      if (lidl !== run || typeof browser?.id !== 'string' || !browser.id) {
        throw Error('Lidl browservenster kon niet veilig worden geopend')
      }
      run.id = browser.id
      run.lidlOrigin = true
      run.url = lidlStore.url
      run.interval = setInterval(() => void inspectLidl(run), 1500)
      void inspectLidl(run)
    } catch {
      await closeLidl()
      say('Lidl kon niet worden geopend; Inhuis heeft geen Lidl-import bevestigd.')
    } finally { opening = false }
    return
  }
  const run = lidl
  if (!run || run.transportNonce !== d.nonce) return
  if (d.kind === 'inhuis-native-lidl-cancel') {
    run.finished = true
    await closeLidl()
    return
  }
  if (d.kind !== 'inhuis-native-lidl-command' || !d.data ||
      d.data.request_id !== run.requestId) return
  const cmd = d.data
  if (cmd.type === 'inhuis:lidl-script') {
    if (!run.handshakeSent) return
    try { await installLidlScript(run, cmd.script) }
    catch {
      run.failed = true
      await transmitLidlToInhuis(run, { type: 'inhuis:lidl-error', request_id: run.requestId,
        message: 'Het Lidl-importscript kon niet veilig worden gestart.' }).catch(() => {})
      say('Het ophalen van Lidl-bonnen is veilig gestopt. De periode blijft hervatbaar.')
      await closeLidl()
    }
    return
  }
  if (cmd.type === 'inhuis:lidl-ack') {
    if (!run.scriptInjected || !/^[0-9]{8,40}$/.test(String(cmd.receipt_id || '')) ||
        typeof cmd.ok !== 'boolean') return
    const ack = JSON.stringify({
      type: 'inhuis:lidl-ack', receipt_id: cmd.receipt_id,
      request_id: run.requestId, ok: cmd.ok,
      ...(typeof cmd.error === 'string' ? { error: cmd.error.slice(0, 240) } : {}),
    })
    const code = `(() => {
      if (window.top !== window || location.origin !== ${JSON.stringify(lidlStore.origin)} ||
          location.pathname !== '/mre/purchase-history' ||
          !window.__inhuisNativeLidlOpener) return;
      window.dispatchEvent(new CustomEvent('inhuis-native-lidl-ack', { detail: ${ack} }));
    })()`
    try { await InAppBrowser.executeScript({ id: run.id, code }) } catch { /* Pending receipt times out. */ }
    return
  }
  if (cmd.type === 'inhuis:lidl-finish' && run.scriptInjected && run.handshakeSent) {
    run.finished = true
    await closeLidl()
    say('Lidl-import door Inhuis bevestigd. Je bent terug in Inhuis.')
  }
}

async function handleLidlMessage(event) {
  const run = lidl
  if (!run || !run.id || event?.id !== run.id) return
  const d = event.detail
  if (lidlNativeEventAllowed(event, run, d)) {
    if (!run.scriptInjected || run.failed) return
    try {
      if (JSON.stringify(d.data).length > 950000) throw Error('Lidl-bonbericht is te groot')
      armLidlWatchdog(run, 'Lidl geeft geen verdere importvoortgang terug. De periode blijft hervatbaar.')
      if (d.data.type === 'inhuis:lidl-progress' && !run.hidden) {
        // Keep the authenticated retailer WebView alive; restore the existing Inhuis view.
        await InAppBrowser.hide({ id: run.id })
        run.hidden = true
      }
      await transmitLidlToInhuis(run, d.data)
      if (d.data.type === 'inhuis:lidl-error') await closeLidl()
    } catch {
      run.failed = true
      await transmitLidlToInhuis(run, { type: 'inhuis:lidl-error', request_id: run.requestId,
        message: 'Lidl-achtergrondimport of bonoverdracht kon niet veilig worden voortgezet.' }).catch(() => {})
      await closeLidl()
    }
    return
  }
  const evidence = acceptEvidence(event, run)
  // Reuse the proved browser-probe route check, but do not confuse its
  // optional DOM marker with proof of a complete import. Only the existing
  // backend confirmed Lidl history/begin and history/complete may finish.
  if (!canBeginLidlImport(run, evidence)) return
  run.historyReached = true
  run.handshakeSent = true
  armLidlWatchdog(run, 'Inhuis bevestigt de Lidl-importperiode niet. Probeer opnieuw.')
  try {
    await transmitLidlToInhuis(run, {
      type: 'inhuis:lidl-handshake', bookmarklet_version: 2, request_id: run.requestId,
    })
  } catch {
    run.failed = true
    say('Lidl kon Inhuis niet bereiken. Er is geen import gestart.')
    await closeLidl()
  }
}

async function startInhuis(url) {
  if (opening || inhuis) return
  const origin = secureInhuisUrl(url)
  if (!origin) { say('Voer het HTTPS-adres van Inhuis in, zonder extra pad of gegevens.'); return }
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'android') {
    say('Deze app kan uitsluitend als native Android-testapp starten.'); return
  }
  opening = true; button.disabled = true
  try {
    const view = await InAppBrowser.openWebView({
      url: origin, javascriptBridgeOrigins: [origin],
      allowScreenshotsFromWebPage: false, preventDeeplink: true,
      persistWebViewData: true, visibleTitle: false,
      openBlankTargetInWebView: true,
    })
    if (typeof view.id !== 'string' || !view.id) throw Error('Missing Inhuis WebView')
    inhuis = { id: view.id, origin, channel: crypto.randomUUID() }
    localStorage.setItem('inhuis-secure-origin', origin)
    say('Inhuis geopend. Meld je aan bij Inhuis en kies Mijn winkelkoppelingen.')
    await advertiseInhuisBridge()
  } catch {
    inhuis = null
    say('Inhuis kon niet beveiligd worden geopend. Controleer het HTTPS-adres en het certificaat.')
  } finally { opening = false; button.disabled = false }
}
async function initialize() {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'android') {
    button.disabled = true; say('Deze app is uitsluitend bedoeld voor Android.'); return
  }
  const stored = secureInhuisUrl(localStorage.getItem('inhuis-secure-origin'))
  if (stored) input.value = stored
  listeners.push(await InAppBrowser.addListener('urlChangeEvent', event => {
    if (ah?.id === event.id) {
      const result = nativeAhReturn(event.url, inhuis?.origin)
      if (result) void finishAh(ah, result)
    }
    if (lidl?.id === event.id) {
      lidl.lidlOrigin = validLidlLocation(event.url)
      lidl.url = isHistoryUrl(lidlStore, event.url) ? event.url : null
      if (!lidl.url) lidl.historyReached = false
      void inspectLidl(lidl)
    }
    if (jumbo?.id === event.id) {
      jumbo.jumboOrigin = validJumboLocation(event.url)
      jumbo.url = isHistoryUrl(store, event.url) ? store.origin + new URL(event.url).pathname : null
      if (!jumbo.jumboOrigin) jumbo.historyReached = false
      void inspect(jumbo)
    }
    if (inhuis?.id === event.id && !String(event.url || '').startsWith(inhuis.origin + '/')) {
      void closeJumbo()
      void closeLidl()
    }
  }))
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if (inhuis?.id === event.id) void advertiseInhuisBridge()
    if (jumbo?.id === event.id) void inspect(jumbo)
    if (lidl?.id === event.id) void inspectLidl(lidl)
  }))
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    if (inhuis?.id === event.id) void handleInhuisMessage(event)
    else if (jumbo?.id === event.id) void handleJumboMessage(event)
    else if (lidl?.id === event.id) void handleLidlMessage(event)
  }))
  listeners.push(await InAppBrowser.addListener('closeEvent', event => {
    if (jumbo?.id === event.id) afterClose(jumbo)
    if (lidl?.id === event.id) afterLidlClose(lidl)
    if (ah?.id === event.id) void finishAh(ah, { path: '/onboarding/winkels', result: 'error' })
    if (inhuis?.id === event.id) {
      inhuis = null
      void closeJumbo()
      void closeLidl()
      if (ah) { const previous = ah; ah = null; if (previous.id) void InAppBrowser.close({ id: previous.id }).catch(() => {}) }
      say('Inhuis is gesloten. Je kunt Inhuis opnieuw openen.')
    }
  }))
}
form.addEventListener('submit', event => {
  event.preventDefault()
  void startInhuis(input.value)
})
void initialize().catch(() => say('Native browserinitialisatie mislukt. Geen gegevens verwerkt.'))
window.addEventListener('pagehide', () => {
  void closeJumbo()
  void closeLidl()
  if (ah) { const previous = ah; ah = null; if (previous.id) void InAppBrowser.close({ id: previous.id }).catch(() => {}) }
  if (inhuis?.id) void InAppBrowser.close({ id: inhuis.id }).catch(() => {})
  for (const listener of listeners) void listener.remove().catch(() => {})
})
