import assert from 'node:assert/strict'
import { secureInhuisUrl, validShellMessage, jumboNativeEventAllowed } from './app-contract.mjs'
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
