import { Capacitor } from '@capacitor/core';
import { InAppBrowser } from '@capgo/capacitor-inappbrowser';
import { stores, isHistoryUrl, probeScript, acceptEvidence } from './probe.mjs';

const status = document.getElementById('status');
const buttons = [...document.querySelectorAll('button')];
const loaded = new Set();
let active = null;
const listeners = [];
function report(message) { status.textContent = message; }
function busy(value) { buttons.forEach(button => { button.disabled = value; }); }
async function inspect(run) {
  if (active !== run || run.phase !== 'history' || !run.id || !isHistoryUrl(run.store, run.url) || run.inspecting) return;
  run.inspecting = true;
  try { await InAppBrowser.executeScript({id: run.id, code: probeScript(run.store, run.nonce)}); }
  catch { if (active === run) run.scriptFailed = true; }
  finally { run.inspecting = false; }
}
function finish(run, failure = false) {
  if (active !== run) return;
  clearInterval(run.timer);
  active = null;
  busy(false);
  if (run.phase === 'login') {
    if (!failure) loaded.add(run.store.name);
    report(run.store.name + ': ' + (failure ? 'Browser openen mislukt.' : 'Teruggekeerd uit winkel. Heb je je kunnen aanmelden? Tik dan op Bonhistorie. Aanmelding is nog niet technisch bewezen.'));
    busy(false);
    return;
  }
  report([
    run.store.name + ' — resultaten',
    'Browser geopend en teruggekeerd: ' + (failure ? 'MISLUKT' : 'GESLAAGD'),
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
    if (!run || !run.id || event.id !== run.id) return;
    run.url = isHistoryUrl(run.store,event.url) ? run.store.url : null;
    void inspect(run);
  }));
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if (active?.id && event.id === active.id) { active.pageLoaded = true; void inspect(active); }
  }));
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    const run = active;
    const evidence = run?.phase === 'history' ? acceptEvidence(event, run) : null;
    if (evidence) run.evidence = {history:true,markers:Boolean(run.evidence?.markers || evidence.markers)};
  }));
  listeners.push(await InAppBrowser.addListener('closeEvent', event => {
    if (active?.id && event.id === active.id) finish(active);
  }));
  for (const [key,store] of Object.entries(stores)) {
    document.getElementById(key).addEventListener('click', () => void open(store, 'login'));
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
  const run = {store,nonce:crypto.randomUUID(),id:null,url:null,phase,evidence:null,inspecting:false};
  active = run;
  report(store.name + ' wordt geopend…');
  try {
    const {id} = await InAppBrowser.openWebView({
      url:phase === 'login' ? store.startUrl : store.url, javascriptBridgeOrigins:phase === 'history' ? [store.origin] : [],
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
