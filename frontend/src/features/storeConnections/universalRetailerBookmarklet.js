import { JUMBO_BOOKMARKLET_VERSION } from './jumboReceiptPocBridge.js'
import { LIDL_BOOKMARKLET_VERSION } from './lidlWebReceiptBridge.js'

// Reuse the two existing import programs verbatim. Dispatch only on exact
// retailer origins; never run either on Inhuis or an unrelated website.
export function buildUniversalRetailerBookmarklet(jumbo, lidl) {
  if (!jumbo.startsWith('javascript:') || !lidl.startsWith('javascript:')) {
    throw new Error('Ongeldige winkelbladwijzer')
  }
  const jumboSource = decodeURIComponent(jumbo.slice('javascript:'.length))
  const lidlSource = lidl.slice('javascript:'.length)
  const source = '(function(){if(location.origin==="https://www.jumbo.com"){void (' + jumboSource +
    ');}else if(location.origin==="https://www.lidl.nl"){void (' + lidlSource +
    ');}else{alert("Open eerst Jumbo of Lidl via Inhuis.");}})()'
  return 'javascript:' + encodeURIComponent(source)
}

// A browser-session hint only. It never proves installation or a connection.
// Jumbo's existing v14 script has a fixed date range and callback route.
// Lidl's existing v2 script gets its current date range from Inhuis.
export function mobileBookmarkletSetupKeys(path, from, to) {
  return {
    jumbo: 'jumbo:' + JUMBO_BOOKMARKLET_VERSION + ':' + LIDL_BOOKMARKLET_VERSION + ':' + path + ':' + from + ':' + to,
    lidl: 'lidl:' + LIDL_BOOKMARKLET_VERSION,
  }
}

function hintKey(signature) {
  return 'inhuis:mobile-bookmarklet:1:' + signature.split(':')[0]
}

export function hasMobileBookmarkletSetup(signature, storage) {
  try { return Boolean(signature && (storage || globalThis.sessionStorage).getItem(hintKey(signature)) === signature) }
  catch { return false }
}

export function rememberMobileBookmarkletSetup(keys, storage) {
  try {
    for (const signature of Object.values(keys || {})) (storage || globalThis.sessionStorage).setItem(hintKey(signature), signature)
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
