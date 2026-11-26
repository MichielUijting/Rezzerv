import { Capacitor } from '@capacitor/core';
import { InAppBrowser } from '@capgo/capacitor-inappbrowser';
import { stores, isHistoryUrl, probeScript, acceptEvidence, jumboStateScript, acceptJumboState, jumboTransition, jumboOpenLoginScript, acceptJumboAction, routeCategory, appendDiagnostic, diagnosticScript, acceptDiagnostic, jumboReceiptTestScript, acceptJumboApi } from './probe.mjs';

const status = document.getElementById('status');
const buttons = [...document.querySelectorAll('button')];
const loaded = new Set();
let active = null;
let previousDiagnosticCookie = null;
const listeners = [];
function report(message) { status.textContent = message; }
function busy(value) { buttons.forEach(button => { button.disabled = value; }); }
async function inspect(run) {
  if(active===run && run.phase==='diagnose'){
    if(!run.id || !run.jumboOrigin || run.inspecting)return;
    run.inspecting=true;
    try{await InAppBrowser.executeScript({id:run.id,code:diagnosticScript(run.nonce)});}catch{appendDiagnostic(run,'Diagnosescript niet uitgevoerd');}finally{run.inspecting=false;}
    return;
  }
  if (active !== run || (run.phase !== 'history' && run.phase !== 'combined') || !run.id || run.inspecting) return;
  const history = isHistoryUrl(run.store,run.url);
  const navigation = run.store===stores.jumbo && run.jumboOrigin;
  // A Nuxt route can change without a native URL or page-loaded callback.
  if(!history && !navigation) return;
  run.inspecting = true;
  try { await InAppBrowser.executeScript({id: run.id, code: navigation ? jumboStateScript(run.nonce)+';'+probeScript(run.store,run.nonce) : probeScript(run.store,run.nonce)}); }
  catch { if (active === run) run.scriptFailed = true; }
  finally { run.inspecting = false; }
}
function finish(run, failure = false) {
  if (active !== run) return;
  clearInterval(run.timer);
  active = null;
  busy(false);
  if(run.phase==='diagnose'){
    const previous=previousDiagnosticCookie;
    previousDiagnosticCookie=run.cookieSeen;
    report(['Jumbo diagnose 0.1.10','Cookievenster gezien: '+(run.cookieSeen?'JA':'NIET AANGETOOND'),'Vorige diagnose in deze appsessie: '+(previous===null?'geen':previous?'cookievenster gezien':'cookievenster niet gezien'),'Nieuw browservenster: '+(run.popupSeen?'JA':'NIET AANGETOOND'),'Volgorde van waarnemingen:',...run.trace,'Geen wachtwoorden, cookie-inhoud, URL-parameters of bongegevens opgeslagen.'].join(String.fromCharCode(10)));
    return;
  }
  if (run.phase === 'login') {
    if (!failure) loaded.add(run.store.name);
    report(run.store.name + ': ' + (failure ? 'Browser openen mislukt.' : 'Teruggekeerd uit winkel. Heb je je kunnen aanmelden? Tik dan op Bonhistorie. Aanmelding is nog niet technisch bewezen.'));
    busy(false);
    return;
  }
  report([
    run.store.name + ' — resultaten',
    'Browser geopend en teruggekeerd: ' + (failure ? 'MISLUKT' : 'GESLAAGD'),
    ...(run.store === stores.jumbo ? ['Cookievenster gezien: ' + (run.cookieSeen ? 'JA' : 'NIET AANGETOOND'), 'Accountbediening geprobeerd: ' + (run.accountAttempted ? 'JA' : 'NEE'), 'Accountklik uitgevoerd: ' + (run.accountClicked ? 'JA' : 'NIET BEVESTIGD'), 'Aanmeldbediening geprobeerd: ' + (run.loginAttempted ? 'JA' : 'NEE'), 'Aanmeldklik uitgevoerd: ' + (run.loginClicked ? 'JA' : 'NIET BEVESTIGD'), 'Aanmeldformulier gezien: ' + (run.loginSeen ? 'JA' : 'NIET AANGETOOND'), 'Laatste processtap: ' + ({cookies:'Cookiekeuze',login:'Aanmelden',authenticated:'Aanmeldindicatie',login_available:'Aanmeldknop',account_available:'Accountbediening',receipts_available:'Bonnetjes beschikbaar',error:'Jumbo foutpagina; automatisering gestopt',unknown:'Onbekend'}[run.jumboState] || 'Onbekend'), 'Automatische navigatie geprobeerd: ' + (run.navigationAttempted ? 'JA' : 'NEE'), 'Bonnetjesklik uitgevoerd: ' + (run.navigationAccepted ? 'JA' : 'NEE'), 'Jumbo historieroute bereikt: ' + (run.historyReached ? 'JA' : 'NEE'), 'Historieroute in webpagina waargenomen: ' + (run.historyObserved ? 'JA' : 'NEE'), 'Geverifieerde historie: ' + (run.evidence?.markers ? 'JA' : 'NEE'), 'Terugkeer: ' + (run.autoCloseRequested && ['detail','empty'].includes(run.api?.stage) ? 'AUTOMATISCH' : failure ? 'TECHNISCHE FOUT' : 'HANDMATIG / GEANNULEERD'), 'Scriptfout gemeld: ' + (run.scriptFailed ? 'JA' : 'NEE')] : []),
    'Beveiligde browsercommunicatie: ' + (run.evidence?.history ? 'GESLAAGD' : 'NIET AANGETOOND'),
    'Herkenbare historie-elementen: ' + (run.evidence?.markers ? 'GEZIEN' : 'NIET AANGETOOND'),
    ...(run.store===stores.jumbo?['GraphQL: '+(run.api?.stage||'geen resultaat'),'HTTP: '+(run.api?.http||'onbekend'),'Aantal bonnen: '+(run.api?.count??'onbekend'),'Volledige boninhoud ontvangen: '+(run.api?.detail?'JA':'NIET AANGETOOND'),'Artikelen: nog niet geparseerd',...run.trace]:[]),
    'Bonnen daadwerkelijk geïmporteerd: NEE (niet onderdeel van deze proef).',
    'Een historiescherm bewijst geen volledige bonimport.'
  ].join(String.fromCharCode(10)));
}
async function initialize() {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'android') {
    busy(true); report('Deze proef werkt uitsluitend in de afzonderlijke Android-testapp.'); return;
  }
  listeners.push(await InAppBrowser.addListener('urlChangeEvent', event => {
    const run = active;
    if(run?.phase==='diagnose' && run.popupIds.has(event.id)){appendDiagnostic(run,'Popup route: '+routeCategory(event.url));return;}
    if (!run || !run.id || event.id !== run.id) return;
    if(run.phase==='diagnose')appendDiagnostic(run,'Hoofdvenster route: '+routeCategory(event.url));
    if(run.store===stores.jumbo){try{const u=new URL(event.url);run.jumboOrigin=u.origin===run.store.origin && !u.username && !u.password;}catch{run.jumboOrigin=false;}}
    run.url = isHistoryUrl(run.store,event.url) ? run.store.origin + new URL(event.url).pathname : null;
    if (run.store === stores.jumbo) { run.historyLoaded = false; if (run.url) run.historyReached = true; }
    void inspect(run);
  }));
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if(active?.phase==='diagnose' && active.popupIds.has(event.id)){appendDiagnostic(active,'Popup pagina geladen');return;}
    if(active?.phase==='diagnose' && active.id===event.id)appendDiagnostic(active,'Hoofdvenster pagina geladen');
    if (active?.id && event.id === active.id) { active.pageLoaded = true; if (active.store === stores.jumbo && isHistoryUrl(active.store,active.url)) active.historyLoaded = true; void inspect(active); }
  }));
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    const run = active;
    if(run?.phase==='diagnose'){
      const label=acceptDiagnostic(event,run);
      if(label){if(label==='Cookievenster zichtbaar')run.cookieSeen=true;appendDiagnostic(run,label);}
      return;
    }
    const api=acceptJumboApi(event,run);
    if(api){run.api=api; if(['detail','empty'].includes(api.stage)&&!run.closing&&!run.manual){run.closing=true;run.autoCloseRequested=true;void InAppBrowser.close({id:run.id}).catch(()=>{run.closing=false;run.autoCloseRequested=false;run.scriptFailed=true;});}return;}
    const state=acceptJumboState(event,run);
    if(state){
      appendDiagnostic(run,'Toestand: '+state);
      const action=jumboTransition(run,state);
      // Never force a guessed Jumbo route; use the retailer's actual receipt control.
      if(action==='login' || action==='receipts')void InAppBrowser.executeScript({id:run.id,code:jumboOpenLoginScript(run.nonce,action)}).catch(()=>{run.scriptFailed=true;});
      return;
    }
    const signal=acceptJumboAction(event,run);
    if(signal){if(signal.action==='receipts'){run.navigationAccepted=signal.acted;appendDiagnostic(run,'Routerklik bevestigd: '+(signal.acted?'JA':'NEE'));if(!signal.acted && (run.retries||0)<5){run.retries=(run.retries||0)+1;run.navigationAttempted=false;}} if(signal.action==='account')run.accountClicked=signal.acted; if(signal.action==='login')run.loginClicked=signal.acted; return;}
    const evidence = (run?.phase === 'history' || run?.phase === 'combined') ? acceptEvidence(event, run) : null;
    if (evidence) {
      if(run.store===stores.jumbo){run.historyReached=true;run.historyObserved=true;}
      run.evidence = {history:true,markers:Boolean(run.evidence?.markers || evidence.markers)};
      if(run.store===stores.jumbo && event.detail.route==='bestellingen' && !run.apiRequested && !run.blocked){run.apiRequested=true;void InAppBrowser.executeScript({id:run.id,code:jumboReceiptTestScript(run.nonce)}).catch(()=>{run.scriptFailed=true;});}
    }
  }));
  listeners.push(await InAppBrowser.addListener('popupWindowOpened', event=>{
    const run=active;
    if(run?.phase!=='diagnose' || !run.id || !(event.parentId===run.id || run.popupIds.has(event.parentId)))return;
    run.popupIds.add(event.id);run.popupSeen=true;
    appendDiagnostic(run,'Nieuw browservenster: '+routeCategory(event.url));
  }));
  listeners.push(await InAppBrowser.addListener('closeEvent', event => {
    if(active?.phase==='diagnose' && active.popupIds.has(event.id)){active.popupIds.delete(event.id);appendDiagnostic(active,'Popup gesloten');return;}
    if (active?.id && event.id === active.id) finish(active);
  }));
  document.getElementById('jumbo-diagnose').addEventListener('click',()=>void open(stores.jumbo,'diagnose'));
  document.getElementById('jumbo-api').addEventListener('click',()=>void open(stores.jumbo,'combined',true));
  for (const [key,store] of Object.entries(stores)) {
    document.getElementById(key).addEventListener('click', () => void open(store, key === 'jumbo' ? 'combined' : 'login'));
    if (key === 'jumbo') continue;
    document.getElementById(key+'-history').addEventListener('click', () => {
      if (!loaded.has(store.name)) { report('Open eerst '+store.name+' en meld je aan op de winkelwebsite.'); return; }
      void open(store, 'history');
    });
  }
  busy(false);
}
async function open(store, phase = 'login', manual=false) {
  if (active) return;
  busy(true);
  const run = {store,nonce:crypto.randomUUID(),id:null,url:null,phase,manual,evidence:null,inspecting:false,trace:[],popupIds:new Set(),cookieSeen:false,historyLoaded:false};
  active = run;
  report(store.name + ' wordt geopend…');
  try {
    const {id} = await InAppBrowser.openWebView({
      url:phase === 'history' ? store.url : store.startUrl, javascriptBridgeOrigins:phase === 'login' ? [] : [store.origin],
      allowScreenshotsFromWebPage:false, preventDeeplink:true,
      persistWebViewData:true,
      visibleTitle:true, openBlankTargetInWebView:true
    });
    if (typeof id !== 'string' || !id) throw Error('Missing native id');
    run.id = id;
    // Jumbo scripts independently guard origin/path and can observe same-document navigation.
    if(store===stores.jumbo)run.jumboOrigin=true;
    run.timer = setInterval(() => void inspect(run), 1500);
    void inspect(run);
  } catch { finish(run,true); }
}
busy(true);
initialize().catch(() => { busy(true); report('De native browsercomponent is niet beschikbaar.'); });
window.addEventListener('pagehide', () => {
  if (active) { clearInterval(active.timer); if (active.id) void InAppBrowser.close({id:active.id}).catch(()=>{}); active = null; }
  for (const listener of listeners) void listener.remove().catch(()=>{});
});
