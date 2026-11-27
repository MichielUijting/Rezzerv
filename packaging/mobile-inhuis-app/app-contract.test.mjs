import assert from 'node:assert/strict'
import { secureInhuisUrl, validShellMessage, jumboNativeEventAllowed, lidlNativeEventAllowed } from './app-contract.mjs'
assert.equal(secureInhuisUrl('https://inhuis.example.nl'), 'https://inhuis.example.nl')
for (const url of ['http://inhuis.example.nl', 'https://inhuis.example.nl?token=secret',
  'https://user:pw@inhuis.example.nl', 'https://inhuis.example.nl:8011',
  'https://www.jumbo.com', 'file:///index.html', 'https://inhuis.example.nl/path']) {
  assert.equal(secureInhuisUrl(url), null)
}
const id='view-1',channel='b2766412-f716-4b33-a154-7491b2650480'
const data={kind:'inhuis-native-jumbo-start',channel,nonce:'c1794e11-13a8-4ddd-a3a2-cc61cffaecea'}
assert.equal(validShellMessage({id},id,channel,'https://inhuis.example.nl',data),true)
assert.equal(validShellMessage({id:'other'},id,channel,'https://inhuis.example.nl',data),false)
assert.equal(validShellMessage({id},id,'other','https://inhuis.example.nl',data),false)
const run={id:'jumbo-view',jumboOrigin:true,nonce:data.nonce,requestId:'test-request'}
const payload={kind:'inhuis-native-jumbo-data',nonce:run.nonce,
  data:{type:'inhuis:jumbo-complete',request_id:run.requestId,version:14,source_origin:'https://www.jumbo.com'}}
assert.equal(jumboNativeEventAllowed({id:'jumbo-view'},run,payload),true)
assert.equal(jumboNativeEventAllowed({id:'untrusted'},run,payload),false)
assert.equal(jumboNativeEventAllowed({id:'jumbo-view'},{...run,jumboOrigin:false},payload),false)
console.log('Android shell protocol contracts: OK')

const lidlRun={id:'lidl-view',lidlOrigin:true,nonce:data.nonce,requestId:'lidl-request'}
const lidlData={kind:'inhuis-native-lidl-data',nonce:data.nonce,
  data:{type:'inhuis:lidl-receipt',request_id:'lidl-request'}}
assert.equal(lidlNativeEventAllowed({id:'lidl-view'},lidlRun,lidlData),true)
assert.equal(lidlNativeEventAllowed({id:'wrong'},lidlRun,lidlData),false)
assert.equal(lidlNativeEventAllowed({id:'lidl-view'},lidlRun,{...lidlData,nonce:'bad'}),false)
assert.equal(lidlNativeEventAllowed({id:'lidl-view'},lidlRun,
  {...lidlData,data:{...lidlData.data,request_id:'other'}}),false)
assert.equal(lidlNativeEventAllowed({id:'lidl-view'},lidlRun,
  {...lidlData,data:{...lidlData.data,type:'inhuis:lidl-ack'}}),false)
assert.equal(validShellMessage({id},id,channel,'https://inhuis.example.nl',
  {...data,kind:'inhuis-native-lidl-start'}),true)
const appSource=(await import('node:fs')).readFileSync(new URL('./app.mjs', import.meta.url),'utf8')
for(const name of ['handleInhuisLidlMessage','handleLidlMessage','installLidlScript','transmitLidlToInhuis',
  'lidlNativeEventAllowed','inhuis-native-lidl-ack','inhuis:lidl-finish','closeLidl']) assert.match(appSource,new RegExp(name))
assert.match(appSource, /safeJumboOwner\(d.binding\)/)
