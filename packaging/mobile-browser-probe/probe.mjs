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
      : Array.from(document.querySelectorAll('h1,h2,h3,h4,main a,main button,[role=heading]'))
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

 // Navigation only through the retailer's own visible account menu.
export function jumboNavigationScript(nonce) {
 const config=JSON.stringify({origin:stores.jumbo.origin,nonce});
 return `(() => {
 const c=${config};
 if(window.top!==window || location.origin!==c.origin || /login|signin|oauth|auth/i.test(location.pathname)) return;
 if(typeof window.mobileApp?.postMessage!=='function') return;
 const visible=e=>e.getClientRects().length>0;
 if(Array.from(document.querySelectorAll('input[type="password"]')).some(visible)) return;
 const links=Array.from(document.querySelectorAll('a[href]')).filter(visible);
 const logout=links.some(e=>/^(uitloggen|afmelden|log uit)$/i.test(e.textContent.trim())) ||
 Array.from(document.querySelectorAll('button')).filter(visible).some(e=>/^(uitloggen|afmelden|log uit)$/i.test(e.textContent.trim()));
 const target=links.find(e=>{try{const u=new URL(e.href,location.origin);return u.origin===c.origin && !u.username && !u.password && ['/bestellingen','/orders'].includes(u.pathname) && /bestellingen/i.test(e.textContent.trim());}catch{return false;}});
 if(logout && target) window.mobileApp.postMessage({detail:{kind:'inhuis-jumbo-navigation',nonce:c.nonce,ready:true}});
 })();`;
}
export function acceptJumboNavigation(event,run) {
 return Boolean(run && run.store===stores.jumbo && run.phase==='combined' && run.id && event?.id===run.id && run.jumboOrigin && !run.navigationAttempted && !run.historyReached && event.detail?.kind==='inhuis-jumbo-navigation' && event.detail.nonce===run.nonce && event.detail.ready===true);
}
export function jumboNavigateScript() {
 return `(() => {
 if(window.top!==window || location.origin!=='https://www.jumbo.com' || /login|signin|oauth|auth/i.test(location.pathname))return;
 const visible=e=>e.getClientRects().length>0;
 if(Array.from(document.querySelectorAll('input[type="password"]')).some(visible))return;
 const logout=Array.from(document.querySelectorAll('a,button')).filter(visible).some(e=>/^(uitloggen|afmelden|log uit)$/i.test(e.textContent.trim()));
 const target=Array.from(document.querySelectorAll('a[href]')).filter(visible).find(e=>{try{const u=new URL(e.href,location.origin);return u.origin===location.origin && !u.username && !u.password && ['/bestellingen','/orders'].includes(u.pathname) && /bestellingen/i.test(e.textContent.trim());}catch{return false;}});
 if(logout && target) target.click();
 })();`;
}
