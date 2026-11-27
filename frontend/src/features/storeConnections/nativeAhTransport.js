import { readStoredAuthContext } from '../../lib/authSession.js'
import { snapshotJumboImportContext } from './jumboImportContext.js'
import { nativeJumboShell } from './nativeJumboTransport.js'

// Android opens AH only via the separate trusted Tailscale HTTPS listener
// on port 8443. Inhuis API traffic and callback remain on HTTPS.
export function validNativeAhLoginUrl(value, inhuisOrigin) {
  try {
    const app = new URL(inhuisOrigin)
    const login = new URL(value)
    return app.protocol === 'https:' && app.port === '' &&
      app.hostname.endsWith('.ts.net') && app.hostname.split('.').length >= 3 &&
      login.protocol === 'https:' && login.hostname === app.hostname &&
      login.port === '8443' && !login.username && !login.password &&
      !login.search && !login.hash &&
      /^\/ah-oauth\/launch\/[A-Za-z0-9_-]{20,100}$/.test(login.pathname)
  } catch { return false }
}

export function openNativeAhLogin(loginUrl, win = globalThis.window) {
  const shell = nativeJumboShell(win)
  if (!shell || !validNativeAhLoginUrl(loginUrl, win.location.origin)) return false
  let binding
  try { binding = snapshotJumboImportContext(readStoredAuthContext()) }
  catch { return false }
  const nonce = win.crypto?.randomUUID?.()
  if (!/^[0-9a-f-]{36}$/i.test(String(nonce || ''))) return false
  win.mobileApp.postMessage({ detail: {
    kind: 'inhuis-native-ah-start', channel: shell.channel, nonce,
    binding, url: loginUrl,
  } })
  return true
}
