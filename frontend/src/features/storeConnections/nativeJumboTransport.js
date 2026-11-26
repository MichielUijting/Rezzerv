import { AUTH_CONTEXT_CHANGED_EVENT, readStoredAuthContext } from '../../lib/authSession.js'
import { snapshotJumboImportContext, jumboImportContextMatches } from './jumboImportContext.js'
// Only the separately injected native Inhuis shell supplies this capability.
// Chrome, a regular browser and an installed PWA retain their old flow.
export const JUMBO_NATIVE_ORIGIN = 'https://www.jumbo.com'
export const INHUIS_NATIVE_EVENT = 'inhuis-native-jumbo-event'

export function nativeJumboShell(win = globalThis.window) {
  const shell = win?.__inhuisNativeShell
  return shell?.version === 1 && /^[0-9a-f-]{36}$/i.test(String(shell.channel || '')) &&
    typeof win?.mobileApp?.postMessage === 'function' ? shell : null
}

export function acceptsNativeJumboMessage(message, channel, nonce) {
  const data = message?.detail
  return Boolean(data?.channel === channel && data?.nonce === nonce &&
    data?.kind === 'inhuis-native-jumbo-relay' &&
    data?.data && typeof data.data === 'object' &&
    ['inhuis:jumbo-handshake', 'inhuis:jumbo-batch', 'inhuis:jumbo-complete',
      'inhuis:jumbo-error'].includes(data.data.type))
}

export function startNativeJumboTransport(win = globalThis.window) {
  const shell = nativeJumboShell(win)
  if (!shell) return null
  let boundContext
  try { boundContext = snapshotJumboImportContext(readStoredAuthContext()) }
  catch { return null }
  const nonce = win.crypto?.randomUUID?.()
  if (!/^[0-9a-f-]{36}$/i.test(String(nonce || ''))) return null
  let open = true
  const post = detail => {
    if (!open || !nativeJumboShell(win) || win.__inhuisNativeShell.channel !== shell.channel) return false
    win.mobileApp.postMessage({ detail: { ...detail, channel: shell.channel, nonce } })
    return true
  }
  const source = {
    postMessage(data, targetOrigin) {
      if (targetOrigin !== JUMBO_NATIVE_ORIGIN || !data ||
          !['inhuis:jumbo-script', 'inhuis:jumbo-ack'].includes(data.type)) return
      post({ kind: 'inhuis-native-jumbo-command', data })
    },
    close() {
      if (!open) return
      post({ kind: 'inhuis-native-jumbo-cancel' })
      open = false
      win.removeEventListener(INHUIS_NATIVE_EVENT, relay)
      win.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, authChanged)
    },
  }
  const relay = event => {
    if (!open || !acceptsNativeJumboMessage(event, shell.channel, nonce)) return
    win.dispatchEvent(new CustomEvent('inhuis-jumbo-native-message', {
      detail: { origin: JUMBO_NATIVE_ORIGIN, source, data: event.detail.data },
    }))
  }
  const authChanged = () => {
    if (!jumboImportContextMatches(boundContext, readStoredAuthContext())) source.close()
  }
  source.expectedContext = boundContext
  win.addEventListener(INHUIS_NATIVE_EVENT, relay)
  win.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, authChanged)
  if (!post({ kind: 'inhuis-native-jumbo-start', binding: boundContext })) {
    source.close()
    return null
  }
  return source
}
