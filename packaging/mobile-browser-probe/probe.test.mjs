import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {stores, isHistoryUrl, probeScript, acceptEvidence} from './probe.mjs';

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
