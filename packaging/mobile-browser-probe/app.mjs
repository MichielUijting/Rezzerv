import { Capacitor } from '@capacitor/core';
import { InAppBrowser } from '@capgo/capacitor-inappbrowser';
import { stores, isHistoryUrl, probeScript, acceptEvidence, jumboStateScript, acceptJumboState, jumboTransition, jumboOpenLoginScript, routeCategory, appendDiagnostic, diagnosticScript, acceptDiagnostic } from './probe.mjs';

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
  const navigation = run.store===stores.jumbo && run.jumboOrigin && !history;
  if(!history && !navigation) return;
  run.inspecting = true;
  try { await InAppBrowser.executeScript({id: run.id, code: history ? probeScript(run.store, run.nonce) : jumboStateScript(run.nonce)}); }
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
    report(['Jumbo diagnose 0.1.6','Cookievenster gezien: '+(run.cookieSeen?'JA':'NIET AANGETOOND'),'Vorige diagnose in deze appsessie: '+(previous===null?'geen':previous?'cookievenster gezien':'cookievenster niet gezien'),'Nieuw browservenster: '+(run.popupSeen?'JA':'NIET AANGETOOND'),'Volgorde van waarnemingen:',...run.trace,'Geen wachtwoorden, cookie-inhoud, URL-parameters of bongegevens opgeslagen.'].join(String.fromCharCode(10)));
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
    ...(run.store === stores.jumbo ? ['Cookievenster gezien: ' + (run.cookieSeen ? 'JA' : 'NIET AANGETOOND'), 'Aanmeldbediening geprobeerd: ' + (run.loginAttempted ? 'JA' : 'NEE'), 'Aanmeldformulier gezien: ' + (run.loginSeen ? 'JA' : 'NIET AANGETOOND'), 'Laatste processtap: ' + ({cookies:'Cookiekeuze',login:'Aanmelden',authenticated:'Aanmeldindicatie',login_available:'Aanmeldknop',unknown:'Onbekend'}[run.jumboState] || 'Onbekend'), 'Automatische navigatie geprobeerd: ' + (run.navigationAttempted ? 'JA' : 'NEE'), 'Native navigatie geaccepteerd: ' + (run.navigationAccepted ? 'JA' : 'NEE'), 'Jumbo historieroute bereikt: ' + (run.historyReached ? 'JA' : 'NEE'), 'Pagina geladen gemeld: ' + (run.pageLoaded ? 'JA' : 'NEE'), 'Scriptfout gemeld: ' + (run.scriptFailed ? 'JA' : 'NEE')] : []),
    'Beveiligde browsercommunicatie: ' + (run.evidence?.history ? 'GESLAAGD' : 'NIET AANGETOOND'),
    'Herkenbare historie-elementen: ' + (run.evidence?.markers ? 'GEZIEN' : 'NIET AANGETOOND'),
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
    if (run.store === stores.jumbo && run.url) run.historyReached = true;
    void inspect(run);
  }));
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if(active?.phase==='diagnose' && active.popupIds.has(event.id)){appendDiagnostic(active,'Popup pagina geladen');return;}
    if(active?.phase==='diagnose' && active.id===event.id)appendDiagnostic(active,'Hoofdvenster pagina geladen');
    if (active?.id && event.id === active.id) { active.pageLoaded = true; void inspect(active); }
  }));
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    const run = active;
    if(run?.phase==='diagnose'){
      const label=acceptDiagnostic(event,run);
      if(label){if(label==='Cookievenster zichtbaar')run.cookieSeen=true;appendDiagnostic(run,label);}
      return;
    }
    const state=acceptJumboState(event,run);
    if(state){
      const action=jumboTransition(run,state);
      if(action==='history')void InAppBrowser.setUrl({id:run.id,url:stores.jumbo.url}).then(()=>{run.navigationAccepted=true;}).catch(()=>{run.scriptFailed=true;});
      if(action==='login')void InAppBrowser.executeScript({id:run.id,code:jumboOpenLoginScript()}).catch(()=>{run.scriptFailed=true;});
      return;
    }
    const evidence = (run?.phase === 'history' || run?.phase === 'combined') ? acceptEvidence(event, run) : null;
    if (evidence) {
      run.evidence = {history:true,markers:Boolean(run.evidence?.markers || evidence.markers)};
      if(run.store===stores.jumbo && evidence.markers && !run.closing){run.closing=true;void InAppBrowser.close({id:run.id}).catch(()=>{run.closing=false;run.scriptFailed=true;});}
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
async function open(store, phase = 'login') {
  if (active) return;
  busy(true);
  const run = {store,nonce:crypto.randomUUID(),id:null,url:null,phase,evidence:null,inspecting:false,trace:[],popupIds:new Set(),cookieSeen:false};
  active = run;
  report(store.name + ' wordt geopend…');
  try {
    const {id} = await InAppBrowser.openWebView({
      url:phase === 'history' ? store.url : phase==='diagnose' ? store.origin+'/' : store.startUrl, javascriptBridgeOrigins:phase === 'login' ? [] : [store.origin],
      allowScreenshotsFromWebPage:false, preventDeeplink:true,
      persistWebViewData:true,
      visibleTitle:true, openBlankTargetInWebView:true
    });
    if (typeof id !== 'string' || !id) throw Error('Missing native id');
    run.id = id;
    // Do not assume navigation succeeded; only native URL events establish the route.
    // Poll only while native reports the expected history route. The injected
    // script checks origin and path again, including after any navigation race.
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
