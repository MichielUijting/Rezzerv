import { Capacitor } from '@capacitor/core';
import { InAppBrowser } from '@capgo/capacitor-inappbrowser';
import { stores, isHistoryUrl, probeScript, acceptEvidence } from './probe.mjs';

const status = document.getElementById('status');
const buttons = [document.getElementById('jumbo'), document.getElementById('lidl')];
let active = null;
const listeners = [];
function report(message) { status.textContent = message; }
function busy(value) { buttons.forEach(button => { button.disabled = value; }); }
async function inspect(run) {
  if (active !== run || !run.id || !isHistoryUrl(run.store, run.url) || run.inspecting) return;
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
    run.url = event.url;
    void inspect(run);
  }));
  listeners.push(await InAppBrowser.addListener('browserPageLoaded', event => {
    if (active?.id && event.id === active.id) void inspect(active);
  }));
  listeners.push(await InAppBrowser.addListener('messageFromWebview', event => {
    const run = active;
    const evidence = acceptEvidence(event, run);
    if (evidence) run.evidence = {history:true,markers:Boolean(run.evidence?.markers || evidence.markers)};
  }));
  listeners.push(await InAppBrowser.addListener('closeEvent', event => {
    if (active?.id && event.id === active.id) finish(active);
  }));
  for (const [key,store] of Object.entries(stores)) document.getElementById(key).addEventListener('click', () => void open(store));
  busy(false);
}
async function open(store) {
  if (active) return;
  busy(true);
  const run = {store,nonce:crypto.randomUUID(),id:null,url:store.url,evidence:null,inspecting:false};
  active = run;
  report(store.name + ' wordt geopend…');
  try {
    const {id} = await InAppBrowser.openWebView({
      url:store.url, javascriptBridgeOrigins:[store.origin],
      allowScreenshotsFromWebPage:false, preventDeeplink:true,
      persistWebViewData:false,
      visibleTitle:true, openBlankTargetInWebView:true
    });
    if (typeof id !== 'string' || !id) throw Error('Missing native id');
    run.id = id;
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
