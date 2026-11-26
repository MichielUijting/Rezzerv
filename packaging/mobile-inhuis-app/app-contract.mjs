export const INHUIS_NATIVE_MESSAGE_TYPES = Object.freeze([
  'inhuis:jumbo-batch', 'inhuis:jumbo-complete', 'inhuis:jumbo-error',
])
export function secureInhuisUrl(value) {
  try {
    const url = new URL(String(value || ''))
    if (url.protocol !== 'https:' || url.username || url.password ||
        url.search || url.hash || url.pathname !== '/' ||
        !url.hostname || url.hostname === 'www.jumbo.com' ||
        url.port && url.port !== '443') return null
    return url.origin
  } catch {
    return null
  }
}
export function validShellMessage(event, id, channel, origin, data) {
  return Boolean(event?.id && event.id === id &&
    data?.channel === channel && data?.kind &&
    ['inhuis-native-jumbo-start','inhuis-native-jumbo-command','inhuis-native-jumbo-cancel'].includes(data.kind) &&
    /^[0-9a-f-]{36}$/i.test(String(data.nonce || '')) &&
    origin && secureInhuisUrl(origin) === origin)
}
export function jumboNativeEventAllowed(event, run, data) {
  return Boolean(run?.id && event?.id === run.id && run.jumboOrigin &&
    data?.nonce === run.nonce && data.kind === 'inhuis-native-jumbo-data' &&
    data.data && INHUIS_NATIVE_MESSAGE_TYPES.includes(data.data.type) &&
    data.data.request_id === run.requestId &&
    data.data.version === 14 && data.data.source_origin === 'https://www.jumbo.com')
}
