import { Capacitor } from '@capacitor/core'
import { InAppBrowser } from '@capgo/capacitor-inappbrowser'
import {
  stores, isHistoryUrl, probeScript, acceptEvidence, jumboStateScript,
  acceptJumboState, jumboTransition, jumboOpenLoginScript, acceptJumboAction,
} from './probe.mjs'
import {
  secureInhuisUrl, validShellMessage, jumboNativeEventAllowed,
} from './app-contract.mjs'

const form = document.getElementById('connect')
const input = document.getElementById('inhuis-url')
const status = document.getElementById('status')
const button = form.querySelector('button')
const store = stores.jumbo
let inhuis = null
let jumbo = null
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
  await InAppBrowser.executeScript({ id: run.id, code: shim })
  run.scriptInjected = true
  await InAppBrowser.executeScript({ id: run.id, code: script })
}
async function handleInhuisMessage(event) {
  const runShell = inhuis
  const d = event?.detail
  if (!runShell || !validShellMessage(event, runShell.id, runShell.channel, runShell.origin, d)) return
  if (d.kind === 'inhuis-native-jumbo-start') {
    if (jumbo || opening) return
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
    if (jumbo?.id === event.id) {
      jumbo.jumboOrigin = validJumboLocation(event.url)
      jumbo.url = isHistoryUrl(store, event.url) ? store.origin + new URL(event.url).pathname : null
      if (!jumbo.jumboOrigin) jumbo.historyReached = false
      void inspect(jumbo)
    }
    if (inhuis?.id === event.id && !String(event.url || '').startsWith(inhuis.origin + '/')) {
      void closeJumbo()
    }
  }))
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if (inhuis?.id === event.id) void advertiseInhuisBridge()
    if (jumbo?.id === event.id) void inspect(jumbo)
  }))
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    if (inhuis?.id === event.id) void handleInhuisMessage(event)
    else if (jumbo?.id === event.id) void handleJumboMessage(event)
  }))
  listeners.push(await InAppBrowser.addListener('closeEvent', event => {
    if (jumbo?.id === event.id) afterClose(jumbo)
    if (inhuis?.id === event.id) {
      inhuis = null
      void closeJumbo()
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
  if (inhuis?.id) void InAppBrowser.close({ id: inhuis.id }).catch(() => {})
  for (const listener of listeners) void listener.remove().catch(() => {})
})
