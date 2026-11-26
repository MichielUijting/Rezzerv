import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {stores, isHistoryUrl, probeScript, acceptEvidence, jumboStateScript, acceptJumboState, jumboTransition, jumboOpenLoginScript} from './probe.mjs';

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
  const document={querySelectorAll:()=>markers?[{textContent:'Kassabonnen'}]:[]};
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
 const document={querySelectorAll:s=>s==='h1,h2,h3,h4,[role=heading]'?[...(title?[{textContent:'Bestellingen'}]:[]),...(completed?[{textContent:'Afgerond'}]:[])]:s==='a,button,[role=button]'?(row?[{textContent:'Maandag 1 januari 12:00 Jumbo Testwinkel'}]:[]):s==='main p,main [role=status]'?(empty?[{textContent:'Je hebt nog geen bestellingen'}]:[]):[]};
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
 const control={textContent:'Inloggen',getClientRects:()=>[1],closest:()=>null,click:()=>clicks++};
 const dialog={textContent:'Cookies accepteren',getClientRects:()=>[1],click:()=>{throw Error('cookie clicked');}};
 const document={querySelectorAll:s=>s.startsWith('#onetrust')?(cookie?[dialog]:[]):s.startsWith('input')?[]:[control]};
 const window={mobileApp:{postMessage:m=>messages.push(m)}};window.top=window;
 const ctx={window,document,location:{origin:stores.jumbo.origin,pathname:'/'},getComputedStyle:()=>({visibility:'visible'})};
 vm.runInNewContext(jumboStateScript('n'),ctx);
 vm.runInNewContext(jumboOpenLoginScript(),ctx);
 assert.equal(messages[0].detail.state,cookie?'cookies':'login_available');
 assert.equal(clicks,cookie?0:1);
 }
});
