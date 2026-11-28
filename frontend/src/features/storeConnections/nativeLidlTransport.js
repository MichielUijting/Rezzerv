import { AUTH_CONTEXT_CHANGED_EVENT, readStoredAuthContext } from '../../lib/authSession.js'
import { snapshotJumboImportContext, jumboImportContextMatches } from './jumboImportContext.js'
import { nativeJumboShell } from './nativeJumboTransport.js'
import { LIDL_WEB_ORIGIN, LIDL_BOOKMARKLET_VERSION } from './lidlWebReceiptBridge.js'

export const INHUIS_NATIVE_LIDL_EVENT = 'inhuis-native-lidl-event'
const TYPES = new Set(['inhuis:lidl-handshake', 'inhuis:lidl-progress', 'inhuis:lidl-receipt', 'inhuis:lidl-complete', 'inhuis:lidl-error'])
const REQUEST_ID = /^[0-9a-f-]{36}$/i

export function acceptsNativeLidlMessage(message, channel, nonce, requestId = '') {
  const d = message?.detail
  return Boolean(d?.channel === channel && d?.nonce === nonce && d?.kind === 'inhuis-native-lidl-relay' &&
    TYPES.has(d?.data?.type) && REQUEST_ID.test(String(d?.data?.request_id || '')) &&
    (!requestId || d.data.request_id === requestId))
}

export function startNativeLidlTransport(win = globalThis.window) {
  const shell = nativeJumboShell(win)
  if (!shell) return null
  let boundContext
  try { boundContext = snapshotJumboImportContext(readStoredAuthContext()) }
  catch { return null }
  const nonce = win.crypto?.randomUUID?.()
  if (!REQUEST_ID.test(String(nonce || ''))) return null
  let open = true
  const post = detail => {
    if (!open || win.__inhuisNativeShell?.channel !== shell.channel || !nativeJumboShell(win)) return false
    win.mobileApp.postMessage({ detail: { ...detail, channel: shell.channel, nonce } })
    return true
  }
  const source = {
    requestId: '',
    expectedContext: boundContext,
    postMessage(data, targetOrigin) {
      if (targetOrigin !== LIDL_WEB_ORIGIN || !data ||
          !['inhuis:lidl-script', 'inhuis:lidl-ack', 'inhuis:lidl-finish'].includes(data.type) ||
          !source.requestId) return
      post({ kind: 'inhuis-native-lidl-command', data: { ...data, request_id: source.requestId } })
    },
    close() {
      if (!open) return
      post({ kind: 'inhuis-native-lidl-cancel' })
      open = false
      win.removeEventListener(INHUIS_NATIVE_LIDL_EVENT, relay)
      win.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, authChanged)
    },
  }
  const relay = event => {
    if (!open || !acceptsNativeLidlMessage(event, shell.channel, nonce, source.requestId)) return
    if (!source.requestId) {
      if (event.detail.data.type !== 'inhuis:lidl-handshake' ||
          event.detail.data.bookmarklet_version !== LIDL_BOOKMARKLET_VERSION) return
      source.requestId = event.detail.data.request_id
    }
    win.dispatchEvent(new CustomEvent('inhuis-lidl-native-message', {
      detail: { origin: LIDL_WEB_ORIGIN, source, data: event.detail.data },
    }))
  }
  const authChanged = () => {
    if (!jumboImportContextMatches(boundContext, readStoredAuthContext())) source.close()
  }
  win.addEventListener(INHUIS_NATIVE_LIDL_EVENT, relay)
  win.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, authChanged)
  if (!post({ kind: 'inhuis-native-lidl-start', binding: boundContext })) {
    source.close()
    return null
  }
  return source
}
