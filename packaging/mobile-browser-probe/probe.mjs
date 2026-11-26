export const stores = Object.freeze({
  jumbo: Object.freeze({ name: 'Jumbo', startUrl: 'https://www.jumbo.com/', origin: 'https://www.jumbo.com', path: '/bestellingen', alternatePath: '/orders', url: 'https://www.jumbo.com/bestellingen' }),
  lidl: Object.freeze({ name: 'Lidl', startUrl: 'https://www.lidl.nl/', origin: 'https://www.lidl.nl', path: '/mre/purchase-history', url: 'https://www.lidl.nl/mre/purchase-history?client_id=NetherlandsEcommerceClient&country_code=nl&language=nl-NL&page=1' })
});
export function isHistoryUrl(store, value) {
  try {
    const url = new URL(value);
    return url.origin === store.origin && (url.pathname === store.path || (store === stores.jumbo && url.pathname === store.alternatePath)) && !url.username && !url.password;
  } catch { return false; }
}
// No HTML, credentials, cookies, receipt identifiers, URLs or content leave the webview.
// The only transmitted evidence is a boolean DOM observation, not authentication.
export function probeScript(store, nonce) {
  const config = JSON.stringify({origin: store.origin, paths: store === stores.jumbo ? [store.path, store.alternatePath] : [store.path], nonce, lidl: store === stores.lidl});
  return `(() => {
    const c = ${config};
    if (window.top !== window || location.origin !== c.origin || !c.paths.includes(location.pathname)) return;
    if (typeof window.mobileApp?.postMessage !== 'function') return;
    const markers = c.lidl
      ? document.querySelectorAll('a[href*="/mre/purchase-detail"]').length > 0
      : Array.from(document.querySelectorAll('main h1,main h2,main h3,main a,main button'))
        .some(node => /\\b(kassabonnen?|winkelbonnen?|digitale bonnen?)\\b/i.test(node.textContent || ''));
    window.mobileApp.postMessage({detail:{kind:'inhuis-history-probe',nonce:c.nonce,history:true,markers:Boolean(markers)}});
  })();`;
}
export function acceptEvidence(event, active) {
  if (!active || !active.id || event?.id !== active.id || !isHistoryUrl(active.store, active.url)) return null;
  const d = event.detail;
  if (!d || d.kind !== 'inhuis-history-probe' || d.nonce !== active.nonce ||
      d.history !== true || typeof d.markers !== 'boolean') return null;
  return {history: true, markers: d.markers};
}
