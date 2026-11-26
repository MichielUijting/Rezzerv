import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {stores, isHistoryUrl, probeScript, acceptEvidence, jumboNavigationScript, acceptJumboNavigation, jumboNavigateScript} from './probe.mjs';

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

test('navigation needs current Jumbo view, nonce and positive evidence only once',()=>{
 const r={store:stores.jumbo,phase:'combined',id:'j',nonce:'n',jumboOrigin:true};
 const e={id:'j',detail:{kind:'inhuis-jumbo-navigation',nonce:'n',ready:true}};
 assert.equal(acceptJumboNavigation(e,r),true);
 for(const change of [{jumboOrigin:false},{navigationAttempted:true},{historyReached:true},{store:stores.lidl},{id:'other'},{nonce:'other'}])assert.equal(acceptJumboNavigation(e,{...r,...change}),false);
});
test('navigation script only uses visible retailer link after logout control is present',()=>{
 for(const [logout,origin,path,expected] of [[true,'https://www.jumbo.com','/account',1],[false,'https://www.jumbo.com','/account',0],[true,'https://evil.example','/account',0],[true,'https://www.jumbo.com','/login',0]]){
 let clicks=0;const messages=[];
 const link={href:'https://www.jumbo.com/bestellingen',textContent:'Bestellingen',getClientRects:()=>[1],click:()=>clicks++};
 const out={textContent:'Uitloggen',getClientRects:()=>[1]};
 const document={querySelectorAll:s=>s.includes('password')?[]:s==='a[href]'?[link]:logout?[out]:[]};
 const window={mobileApp:{postMessage:m=>messages.push(m)}};window.top=window;
 const ctx={window,document,location:{origin,pathname:path},URL};
 vm.runInNewContext(jumboNavigationScript('n'),ctx);vm.runInNewContext(jumboNavigateScript(),ctx);
 assert.equal(messages.length,expected);assert.equal(clicks,expected);
 }
});
