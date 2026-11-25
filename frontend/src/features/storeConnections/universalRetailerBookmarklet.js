import { JUMBO_BOOKMARKLET_VERSION } from './jumboReceiptPocBridge.js'
import { LIDL_BOOKMARKLET_VERSION } from './lidlWebReceiptBridge.js'

// The installed favorite never contains dates, household information or a
// callback path. Jumbo gets its period from the Inhuis tab that opened it.
export function buildUniversalRetailerBookmarklet(inhuisOrigin, lidl) {
  let origin
  try {
    const url = new URL(inhuisOrigin)
    if (!['https:', 'http:'].includes(url.protocol) || url.origin !== inhuisOrigin ||
        url.username || url.password) throw new Error('invalid')
    origin = url.origin
  } catch {
    throw new Error('Ongeldige Inhuis-herkomst voor winkelbladwijzer')
  }
  if (typeof lidl !== 'string' || !lidl.startsWith('javascript:')) {
    throw new Error('Ongeldige Lidl-bladwijzer')
  }
  const lidlSource = lidl.slice('javascript:'.length)
  const jumboSource = [
    '(function(){',
    'const O=' + JSON.stringify(origin) + ';',
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';',
    'const R=window.opener;',
    'if(!R){alert("Open Jumbo eerst via Bonnen ophalen in Inhuis en laat dat tabblad open.");return;}',
    'const Q=String(Date.now())+"-"+Math.random().toString(36).slice(2);',
    'let active=true;',
    'const stop=()=>{active=false;window.removeEventListener("message",receive);window.clearTimeout(timer);};',
    'function receive(e){',
    'if(!active||e.origin!==O||e.source!==R||!e.data||e.data.type!=="inhuis:jumbo-script"||e.data.request_id!==Q)return;',
    'stop();',
    'if(e.data.bookmarklet_version!==V||typeof e.data.script!=="string"||e.data.script.length>250000||!e.data.script.startsWith("(async()=>{")){alert("Inhuis kon de Jumbo-importperiode niet veilig voorbereiden.");return;}',
    'try{new Function(e.data.script)();}catch(err){alert("Jumbo-import kon niet starten.");}',
    '}',
    'window.addEventListener("message",receive);',
    'const timer=window.setTimeout(()=>{if(active){stop();alert("Inhuis heeft de Jumbo-importperiode niet bevestigd. Probeer opnieuw via Inhuis.");}},30000);',
    'R.postMessage({type:"inhuis:jumbo-handshake",bookmarklet_version:V,request_id:Q},O);',
    '})()',
  ].join('')
  const source = '(function(){if(location.origin==="https://www.jumbo.com"){void (' + jumboSource +
    ');}else if(location.origin==="https://www.lidl.nl"){void (' + lidlSource +
    ');}else{alert("Open eerst Jumbo of Lidl via Inhuis.");}})()'
  return 'javascript:' + encodeURIComponent(source)
}

// A persistent browser hint only, never evidence of installation or login.
// One permanent favorite for both retailers;
// neither dates nor the current onboarding/settings path invalidate the hint.
export function mobileBookmarkletSetupKeys() {
  const signature = 'universal:' + JUMBO_BOOKMARKLET_VERSION + ':' + LIDL_BOOKMARKLET_VERSION + ':live-period-v1'
  return { jumbo: signature, lidl: signature }
}

function hintKey(signature) {
  return 'inhuis:mobile-bookmarklet:1:' + signature.split(':')[0]
}

export function hasMobileBookmarkletSetup(signature, storage) {
  try { return Boolean(signature && (storage || globalThis.localStorage).getItem(hintKey(signature)) === signature) }
  catch { return false }
}

export function rememberMobileBookmarkletSetup(keys, storage) {
  try {
    for (const signature of Object.values(keys || {})) (storage || globalThis.localStorage).setItem(hintKey(signature), signature)
  } catch { /* No persistent guarantee; installation remains optional guidance. */ }
}

// Invoke directly from a user's existing button click. A legacy copy attempt
// also supports local HTTP/Tailscale, where Clipboard API may be absent.
export function copyRetailerBookmarklet(value, agent = globalThis.navigator, doc = globalThis.document) {
  if (!value) return Promise.resolve(false)
  try {
    if (agent?.clipboard?.writeText) {
      return Promise.resolve(agent.clipboard.writeText(value)).then(() => true, () => false)
    }
    if (!doc?.body || typeof doc.execCommand !== 'function') return Promise.resolve(false)
    const field = doc.createElement('textarea')
    const previousFocus = doc.activeElement
    field.value = value
    field.readOnly = true
    field.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0'
    doc.body.appendChild(field)
    try {
      field.focus()
      field.select()
      field.setSelectionRange(0, value.length)
      return Promise.resolve(doc.execCommand('copy') === true)
    } finally {
      field.remove()
      previousFocus?.focus?.()
    }
  } catch { return Promise.resolve(false) }
}
