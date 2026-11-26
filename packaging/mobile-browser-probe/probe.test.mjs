import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {stores, isHistoryUrl, probeScript, acceptEvidence, jumboStateScript, acceptJumboState, jumboTransition, jumboOpenLoginScript, acceptJumboAction} from './probe.mjs';

test('allow only exact HTTPS store history route', () => {
  for (const store of Object.values(stores)) {
    assert.equal(isHistoryUrl(store,store.url),true);
    for (const value of ['https://evil.example'+store.path,store.origin+'.evil.example'+store.path,
      store.origin.replace('https:','http:')+store.path,store.origin+'/login',store.origin+store.path+'/extra']) {
      assert.equal(isHistoryUrl(store,value),false,value);
    }
  }
});
test('native id, nonce, route, type and boolean are mandatory', () => {
  const active = {id:'view-a',store:stores.lidl,url:stores.lidl.url,nonce:'nonce-a'};
  const event = {id:'view-a',detail:{kind:'inhuis-history-probe',nonce:'nonce-a',history:true,markers:false}};
  assert.deepEqual(acceptEvidence(event,active),{history:true,markers:false});
  assert.equal(acceptEvidence({...event,id:'view-b'},active),null);
  assert.equal(acceptEvidence({...event,id:undefined},active),null);
  assert.equal(acceptEvidence(event,{...active,url:'https://www.lidl.nl/login'}),null);
  assert.equal(acceptEvidence({...event,detail:{...event.detail,nonce:'old'}},active),null);
  assert.equal(acceptEvidence({...event,detail:{...event.detail,markers:'yes'}},active),null);
  assert.equal(acceptEvidence(event,null),null);
});
function evaluate(store,{origin=store.origin,path=store.path,frame=false,markers=true}={}) {
  const messages=[];
  const window={mobileApp:{postMessage:value=>messages.push(value)}};
  window.top=frame?{}:window;
  const document={querySelectorAll:s=>{
    if(!markers)return [];
    if(store===stores.lidl)return [{textContent:'Kassabonnen'}];
    if(s==='h1,h2,h3,h4,[role=heading]')return [{textContent:'Bestellingen'},{textContent:'Afgerond'}];
    if(s==='main a,main button,main [role=button],main article,main li')return [{textContent:'Maandag 1 januari 12:00 Jumbo Testwinkel'}];
    return [];
  }};
  vm.runInNewContext(probeScript(store,'nonce-a'),{window,location:{origin,pathname:path},document});
  return JSON.parse(JSON.stringify(messages));
}
test('injected read-only probe never reports on login, foreign origin or frame',()=>{
  for (const store of Object.values(stores)) {
    assert.deepEqual(evaluate(store,{origin:'https://evil.example'}),[]);
    assert.deepEqual(evaluate(store,{path:'/login'}),[]);
    assert.deepEqual(evaluate(store,{frame:true}),[]);
    assert.deepEqual(evaluate(store),[{detail:{kind:'inhuis-history-probe',nonce:'nonce-a',history:true,markers:true}}]);
    assert.deepEqual(evaluate(store,{markers:false}),[{detail:{kind:'inhuis-history-probe',nonce:'nonce-a',history:true,markers:false}}]);
  }
});

test('initial visit uses public HTTPS home, not protected history',()=>{
 for(const store of Object.values(stores)){
 assert.equal(new URL(store.startUrl).origin,store.origin);
 assert.equal(new URL(store.startUrl).pathname,'/');
 assert.equal(isHistoryUrl(store,store.startUrl),false);
 }
});

test('Jumbo accepts exact orders redirect but not other origins, routes or Lidl orders',()=>{
 const s=stores.jumbo;
 assert.equal(isHistoryUrl(s,s.origin+'/orders'),true);
 assert.equal(isHistoryUrl(s,s.origin+'/orders?test=1'),true);
 for(const url of [s.origin+'/orders/extra',s.origin+'/orders-fake','https://evil.example/orders','https://user@www.jumbo.com/orders','http://www.jumbo.com/orders']) assert.equal(isHistoryUrl(s,url),false,url);
 assert.equal(isHistoryUrl(stores.lidl,stores.lidl.origin+'/orders'),false);
 assert.equal(evaluate(s,{path:'/orders'}).length,1);
 assert.deepEqual(evaluate(s,{path:'/orders/extra'}),[]);
 assert.deepEqual(evaluate(s,{path:'/orders',origin:'https://evil.example'}),[]);
 assert.deepEqual(evaluate(stores.lidl,{path:'/orders'}),[]);
 const active={id:'j',store:s,url:s.origin+'/orders',nonce:'n'};
 assert.deepEqual(acceptEvidence({id:'j',detail:{kind:'inhuis-history-probe',nonce:'n',history:true,markers:true}},active),{history:true,markers:true});
});

test('Jumbo screenshot history structure requires title and actual completed row or explicit empty',()=>{
 for(const [title,completed,row,empty,expected] of [[true,true,true,false,true],[true,true,false,false,false],[true,false,false,true,true],[false,true,true,false,false],[true,false,false,false,false]]){
 const messages=[];const window={mobileApp:{postMessage:m=>messages.push(m)}};window.top=window;
 const document={querySelectorAll:s=>s==='h1,h2,h3,h4,[role=heading]'?[...(title?[{textContent:'Bestellingen'}]:[]),...(completed?[{textContent:'Afgerond'}]:[])]:s==='main a,main button,main [role=button],main article,main li'?(row?[{textContent:'Maandag 1 januari 12:00 Jumbo Testwinkel'}]:[]):s==='main p,main [role=status]'?(empty?[{textContent:'Je hebt nog geen bestellingen'}]:[]):[]};
 vm.runInNewContext(probeScript(stores.jumbo,'n'),{window,document,location:{origin:stores.jumbo.origin,pathname:'/orders'}});
 assert.equal(messages[0].detail.markers,expected);
 }
});

test('cookie choice blocks automation; login and history are each attempted only once',()=>{
 const r={};
 assert.equal(jumboTransition(r,'cookies'),null);
 assert.equal(r.cookieSeen,true);
 assert.equal(jumboTransition(r,'login_available'),'login');
 assert.equal(jumboTransition(r,'login_available'),null);
 assert.equal(jumboTransition(r,'login'),null);
 assert.equal(r.loginSeen,true);
 assert.equal(jumboTransition(r,'authenticated'),'history');
 assert.equal(jumboTransition(r,'authenticated'),null);
});
test('state evidence requires exact active Jumbo view and nonce',()=>{
 const r={store:stores.jumbo,phase:'combined',id:'j',nonce:'n',jumboOrigin:true};
 const e={id:'j',detail:{kind:'inhuis-jumbo-state',nonce:'n',state:'cookies'}};
 assert.equal(acceptJumboState(e,r),'cookies');
 for(const change of [{jumboOrigin:false},{id:'other'},{nonce:'other'},{store:stores.lidl}])assert.equal(acceptJumboState(e,{...r,...change}),null);
});
test('cookie dialog precedes login control and is never clicked',()=>{
 for(const cookie of [true,false]){
 let clicks=0;const messages=[];
 const control={textContent:'Inloggen',getClientRects:()=>[1],getAttribute:()=>null,closest:s=>s==='header,[role=banner]'?{}:null,click:()=>clicks++};
 const dialog={textContent:'Cookies accepteren',getClientRects:()=>[1],click:()=>{throw Error('cookie clicked');}};
 const document={querySelectorAll:s=>s.startsWith('#onetrust')?(cookie?[dialog]:[]):s.startsWith('input')?[]:[control]};
 const window={mobileApp:{postMessage:m=>messages.push(m)}};window.top=window;
 const ctx={window,document,location:{origin:stores.jumbo.origin,pathname:'/'},getComputedStyle:()=>({visibility:'visible'})};
 vm.runInNewContext(jumboStateScript('n'),ctx);
 vm.runInNewContext(jumboOpenLoginScript('n','login'),ctx);
 assert.equal(messages[0].detail.state,cookie?'cookies':'login_available');
 assert.equal(clicks,cookie?0:1);
 }
});

test('diagnostic routes never return actual hosts, queries or account identifiers',async()=>{
 const {routeCategory,appendDiagnostic,acceptDiagnostic}=await import('./probe.mjs');
 assert.equal(routeCategory('https://www.jumbo.com/orders?token=secret'),'Historie');
 assert.equal(routeCategory('https://login.jumbo.com/path?code=secret'),'Jumbo ander domein');
 assert.equal(routeCategory('https://example.com/private'),'Extern domein');
 const r={store:stores.jumbo,phase:'diagnose',id:'j',nonce:'n',jumboOrigin:true,trace:[]};
 const e={id:'j',detail:{kind:'inhuis-jumbo-diagnostic',nonce:'n',label:'Cookievenster zichtbaar'}};
 assert.equal(acceptDiagnostic(e,r),'Cookievenster zichtbaar');
 assert.equal(acceptDiagnostic({...e,detail:{...e.detail,label:'secret'}},r),null);
 assert.equal(acceptDiagnostic(e,{...r,jumboOrigin:false}),null);
 appendDiagnostic(r,'a');appendDiagnostic(r,'a');assert.deepEqual(r.trace,['a']);
});

test('Jumbo does not accept generic receipt headings without an actual history row',()=>{
 const messages=[];
 const window={mobileApp:{postMessage:x=>messages.push(x)}};window.top=window;
 const doc={querySelectorAll:s=>s==='h1,h2,h3,h4,[role=heading]'?[{textContent:'Kassabonnen'}]:s.includes('input[')?[]:[{textContent:'Bestellingen'}]};
 vm.runInNewContext(probeScript(stores.jumbo,'strict'),{window,location:{origin:stores.jumbo.origin,pathname:'/orders'},document:doc});
 assert.equal(messages[0].detail.markers,false);
});
test('Jumbo never clicks promotional sign-in outside the official account header',()=>{
 let count=0;const msgs=[];
 const control={textContent:'Inloggen',getClientRects:()=>[1],getAttribute:()=>null,closest:()=>null,click:()=>count++};
 const doc={querySelectorAll:s=>s.startsWith('#onetrust')?[]:s.startsWith('input')?[]:[control]};
 const window={mobileApp:{postMessage:m=>msgs.push(m)}};window.top=window;
 const ctx={window,document:doc,location:{origin:stores.jumbo.origin,pathname:'/'},getComputedStyle:()=>({visibility:'visible',display:'block'})};
 vm.runInNewContext(jumboStateScript('n'),ctx);
 assert.equal(msgs[0].detail.state,'unknown');
 vm.runInNewContext(jumboOpenLoginScript('n','login'),ctx);
 assert.equal(count,0);assert.equal(msgs[1].detail.acted,false);
});
test('Jumbo native action acknowledgements require view, nonce and exact origin',()=>{
 const r={store:stores.jumbo,phase:'combined',id:'j',nonce:'n',jumboOrigin:true};
 const e={id:'j',detail:{kind:'inhuis-jumbo-action',nonce:'n',action:'login',acted:true}};
 assert.deepEqual(acceptJumboAction(e,r),{action:'login',acted:true});
 for(const x of [{id:'wrong'}, {detail:{...e.detail,nonce:'bad'}},{detail:{...e.detail,acted:'yes'}}])assert.equal(acceptJumboAction({...e,...x},r),null);
 assert.equal(acceptJumboAction(e,{...r,jumboOrigin:false}),null);
});
test('Jumbo opens official account before sign-in, at most one of each, never during cookies',()=>{
 const r={};
 assert.equal(jumboTransition(r,'cookies'),null);
 assert.equal(jumboTransition(r,'account_available'),'account');
 assert.equal(jumboTransition(r,'account_available'),null);
 assert.equal(jumboTransition(r,'login_available'),'login');
 assert.equal(jumboTransition(r,'login_available'),null);
 assert.equal(jumboTransition(r,'login'),null);
 assert.equal(jumboTransition(r,'authenticated'),'history');
 assert.equal(jumboTransition(r,'authenticated'),null);
});
