export const stores = Object.freeze({
  jumbo: Object.freeze({ name: 'Jumbo', startUrl: 'https://www.jumbo.com/?login=true', origin: 'https://www.jumbo.com', path: '/bestellingen', alternatePath: '/orders', url: 'https://www.jumbo.com/bestellingen' }),
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
      : (() => {
        // A header or a generic "Kassabonnen" link is not evidence of accessible history.
        const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,[role=heading]'))
          .map(e => (e.textContent || '').trim());
        const title = headings.some(t => /^(mijn\\s+)?bestellingen$/i.test(t));
        const completed = headings.some(t => /^afgerond$/i.test(t));
        const rows = Array.from(document.querySelectorAll('main a,main button,main [role=button],main article,main li'))
          .some(e => {
            const t = (e.textContent || '').replace(/\\s+/g,' ').trim();
            return /\\b(maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|ma|di|wo|do|vr|za|zo)\\s+\\d{1,2}\\s+/i.test(t)
              && /\\b\\d{1,2}[:.]\\d{2}\\b/.test(t) && /\\bjumbo\\b/i.test(t);
          });
        const empty = Array.from(document.querySelectorAll('main p,main [role=status]'))
          .some(e => /^(je hebt nog geen (bestellingen|kassabonnen)|geen bestellingen gevonden)[.!]?$/i.test((e.textContent || '').trim()));
        const loginForm = Array.from(document.querySelectorAll('input[type=password],input[autocomplete=username]'))
          .some(e => e.getClientRects?.().length > 0);
        return title && !loginForm && ((completed && rows) || empty);
      })();
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



export function jumboStateScript(nonce) {
 const config=JSON.stringify({origin:stores.jumbo.origin,nonce});
 return `(() => {
 const c=${config};
 if(window.top!==window || location.origin!==c.origin || typeof window.mobileApp?.postMessage!=='function')return;
 const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none';
 const label=e=>(e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim();
 const cookie=Array.from(document.querySelectorAll('#onetrust-banner-sdk,#onetrust-pc-sdk,[role=dialog],[aria-modal=true],#CybotCookiebotDialog')).filter(visible)
   .some(e=>/cookie|privacyvoorkeur/i.test(e.textContent||'') || /onetrust|cookiebot/i.test(e.id||''));
 const forms=Array.from(document.querySelectorAll('input[type=password],input[autocomplete=username],input[type=email]')).some(visible);
 const controls=Array.from(document.querySelectorAll('a,button,[role=button]')).filter(visible);
 const header=controls.filter(e=>e.closest('header,[role=banner]'));
 const logout=controls.some(e=>/^(uitloggen|afmelden|log uit)$/i.test(label(e)));
 const signIn=header.some(e=>/^(inloggen|aanmelden|log in)$/i.test(label(e)));
 const account=header.some(e=>/^(mijn jumbo|mijn account|account|profiel|account openen|mijn profiel)$/i.test(label(e)));
 const state=cookie?'cookies':forms||/login|signin|oauth|auth/i.test(location.pathname)?'login':
   logout?'authenticated':signIn?'login_available':account?'account_available':'unknown';
 window.mobileApp.postMessage({detail:{kind:'inhuis-jumbo-state',nonce:c.nonce,state}});
 })();`;
}
export function acceptJumboState(event,run) {
 const d=event?.detail;
 return run?.store===stores.jumbo && run.phase==='combined' && run.id && event?.id===run.id && run.jumboOrigin && d?.nonce===run.nonce && d.kind==='inhuis-jumbo-state' && ['cookies','login','authenticated','login_available','account_available','unknown'].includes(d.state) ? d.state : null;
}
export function jumboTransition(run,state) {
 run.jumboState=state;
 if(state==='cookies'){run.cookieSeen=true;return null;}
 if(state==='login'){run.loginSeen=true;return null;}
 if(state==='authenticated' && !run.navigationAttempted && !run.historyReached){run.navigationAttempted=true;return 'history';}
 if(state==='login_available' && !run.loginAttempted && !run.navigationAttempted && !run.historyReached){run.loginAttempted=true;return 'login';}
 if(state==='account_available' && !run.accountAttempted && !run.loginAttempted && !run.navigationAttempted && !run.historyReached){run.accountAttempted=true;return 'account';}
 return null;
}
// Only the official header/banners account or sign-in control may be activated.
// A script dispatch is NOT proof of a trusted user gesture or of a resulting login screen.
export function jumboOpenLoginScript(nonce, action='login'){
 const config=JSON.stringify({origin:stores.jumbo.origin,nonce,action});
 return `(() => {
 const c=${config};
 if(window.top!==window || location.origin!==c.origin || typeof window.mobileApp?.postMessage!=='function')return;
 const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none';
 const label=e=>(e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim();
 const cookie=Array.from(document.querySelectorAll('#onetrust-banner-sdk,#onetrust-pc-sdk,[role=dialog],[aria-modal=true],#CybotCookiebotDialog')).filter(visible)
   .some(e=>/cookie|privacyvoorkeur/i.test(e.textContent||'') || /onetrust|cookiebot/i.test(e.id||''));
 const forms=Array.from(document.querySelectorAll('input[type=password],input[autocomplete=username],input[type=email]')).some(visible);
 const controls=Array.from(document.querySelectorAll('a,button,[role=button]')).filter(visible).filter(e=>e.closest('header,[role=banner]'));
 const expected=c.action==='account'?/^(mijn jumbo|mijn account|account|profiel|account openen|mijn profiel)$/i:/^(inloggen|aanmelden|log in)$/i;
 const matches=controls.filter(e=>expected.test(label(e)) && !e.closest('[role=dialog],[aria-modal=true]'));
 let acted=false;
 if(!cookie && !forms && !/login|signin|oauth|auth/i.test(location.pathname) && matches.length===1){
  try {matches[0].click();acted=true;} catch {}
 }
 window.mobileApp.postMessage({detail:{kind:'inhuis-jumbo-action',nonce:c.nonce,action:c.action,acted}});
 })();`;
}
export function acceptJumboAction(event,run){
 const d=event?.detail;
 return run?.store===stores.jumbo && run.phase==='combined' && run.id===event?.id && run.jumboOrigin &&
   d?.kind==='inhuis-jumbo-action' && d.nonce===run.nonce && ['login','account'].includes(d.action) &&
   typeof d.acted==='boolean' ? {action:d.action,acted:d.acted} : null;
}

export function routeCategory(value) {
 try{
  const u=new URL(value);
  if(u.protocol!=='https:' || u.username || u.password)return 'overig';
  if(u.hostname!=='www.jumbo.com')return u.hostname.endsWith('.jumbo.com')?'Jumbo ander domein':'Extern domein';
  if(['/orders','/bestellingen'].includes(u.pathname))return 'Historie';
  if(/login|signin|oauth|auth/i.test(u.pathname))return 'Aanmeldroute';
  if(/account|profiel|mijn-jumbo/i.test(u.pathname))return 'Account';
  return 'Jumbo overige pagina';
 }catch{return 'Onbekende route';}
}
export function appendDiagnostic(run,label) {
 if(run.trace.length<50 && run.trace.at(-1)!==label)run.trace.push(label);
}
export function diagnosticScript(nonce) {
 const c=JSON.stringify({origin:'https://www.jumbo.com',nonce});
 return `(() => {
 const c=${c};
 if(window.top!==window || location.origin!==c.origin || typeof window.mobileApp?.postMessage!=='function')return;
 const send=label=>window.mobileApp.postMessage({detail:{kind:'inhuis-jumbo-diagnostic',nonce:c.nonce,label}});
 const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
 const cookie=Array.from(document.querySelectorAll('#onetrust-banner-sdk,#onetrust-pc-sdk,[role=dialog],[aria-modal=true],#CybotCookiebotDialog')).filter(visible).some(e=>/cookie|privacyvoorkeur/i.test(e.textContent||'') || /onetrust|cookiebot/i.test(e.id||''));
 const forms=Array.from(document.querySelectorAll('input[type=password],input[autocomplete=username],input[type=email]')).some(visible);
 const controls=Array.from(document.querySelectorAll('a,button,[role=button]')).filter(visible);
 const login=controls.filter(e=>/^(inloggen|aanmelden|log in)$/i.test((e.textContent||'').trim()));
 const account=controls.filter(e=>e.closest('header,[role=banner]') && /^(mijn jumbo|mijn account|account|profiel|account openen|mijn profiel)$/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim()));
 const state=cookie?'Cookievenster zichtbaar':forms?'Aanmeldvelden zichtbaar':controls.some(e=>/^(uitloggen|afmelden|log uit)$/i.test((e.textContent||'').trim()))?'Uitlogbediening zichtbaar':account.length>1?'Meerdere accountbedieningen':account.length===1?'Accountbediening in kop':login.length>1?'Meerdere aanmeldknoppen':login.length===1?'Een aanmeldknop':'Geen bekende bediening';
 if(window.__inhuisDiagState!==state){window.__inhuisDiagState=state;send(state);}
 if(window.__inhuisDiagNonce===c.nonce)return;
 window.__inhuisDiagNonce=c.nonce;
 document.addEventListener('click',event=>{
  if(!event.isTrusted || window.__inhuisDiagNonce!==c.nonce)return;
  const e=event.target?.closest?.('a,button,[role=button]');
  if(!e)return;
  const label=(e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim();
  if(!/^(inloggen|aanmelden|log in|mijn jumbo|account|profiel)$/i.test(label) && !e.closest('header,nav'))return;
  if(e.closest('form,[role=dialog],[aria-modal=true]'))return;
  send(e.tagName==='A'?(e.target==='_blank'?'Handmatige klik: link nieuw venster':'Handmatige klik: link'):'Handmatige klik: knop');
 },true);
 })();`;
}
export function acceptDiagnostic(event,run){
 const d=event?.detail;
 const allowed=['Cookievenster zichtbaar','Aanmeldvelden zichtbaar','Uitlogbediening zichtbaar','Meerdere aanmeldknoppen','Een aanmeldknop','Meerdere accountbedieningen','Accountbediening in kop','Geen bekende bediening','Handmatige klik: link nieuw venster','Handmatige klik: link','Handmatige klik: knop'];
 return run?.phase==='diagnose' && run.store===stores.jumbo && run.id===event?.id && run.jumboOrigin && d?.kind==='inhuis-jumbo-diagnostic' && d.nonce===run.nonce && allowed.includes(d.label)?d.label:null;
}
