export function validNativeAhLaunch(value, appOrigin) {
  try {
    const app = new URL(appOrigin)
    const url = new URL(value)
    return app.protocol === 'https:' && app.port === '' &&
      app.hostname.endsWith('.ts.net') && app.hostname.split('.').length >= 3 &&
      url.protocol === 'http:' && url.hostname === app.hostname && url.port === '8011' &&
      !url.username && !url.password && !url.search && !url.hash &&
      /^\/ah-oauth\/launch\/[A-Za-z0-9_-]{20,100}$/.test(url.pathname)
  } catch { return false }
}
export function nativeAhReturn(value, appOrigin) {
  try {
    const url = new URL(value)
    const app = new URL(appOrigin)
    if (url.origin !== app.origin || url.hash ||
        !['/onboarding/winkels', '/instellingen/winkelkoppelingen'].includes(url.pathname) ||
        url.searchParams.size !== 1 || !['connected', 'error'].includes(url.searchParams.get('ah'))) return null
    return { path: url.pathname, result: url.searchParams.get('ah') }
  } catch { return null }
}
export const INHUIS_NATIVE_MESSAGE_TYPES = Object.freeze([
  'inhuis:jumbo-batch', 'inhuis:jumbo-complete', 'inhuis:jumbo-error',
])
export const INHUIS_NATIVE_LIDL_TYPES = Object.freeze([
  'inhuis:lidl-handshake', 'inhuis:lidl-progress', 'inhuis:lidl-receipt',
  'inhuis:lidl-complete', 'inhuis:lidl-error',
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
    [
      'inhuis-native-jumbo-start','inhuis-native-jumbo-command','inhuis-native-jumbo-cancel',
      'inhuis-native-lidl-start','inhuis-native-lidl-command','inhuis-native-lidl-cancel',
      'inhuis-native-ah-start',
    ].includes(data.kind) &&
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

export function lidlNativeEventAllowed(event, run, data) {
  return Boolean(run?.id && event?.id === run.id && run.lidlOrigin &&
    data?.nonce === run.nonce && data.kind === 'inhuis-native-lidl-data' &&
    data.data && INHUIS_NATIVE_LIDL_TYPES.includes(data.data.type) &&
    data.data.request_id === run.requestId)
}
