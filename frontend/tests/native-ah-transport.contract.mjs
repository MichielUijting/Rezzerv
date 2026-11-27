import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { validNativeAhLoginUrl } from '../src/features/storeConnections/nativeAhTransport.js'
const origin='https://inhuis-work.tailnet-example.ts.net'
const login='http://inhuis-work.tailnet-example.ts.net:8011/ah-oauth/launch/'+'a'.repeat(40)
assert.equal(validNativeAhLoginUrl(login,origin),true)
for(const bad of [login.replace('http:', 'https:'),login.replace(':8011', ':8443'),
  login.replace('inhuis-work.tailnet-example','untrusted.tailnet-example'),
  login+'?code=secret',login.replace('/ah-oauth/launch/', '/api/'),
  'http://localhost:8011/ah-oauth/launch/'+'a'.repeat(40)]) {
  assert.equal(validNativeAhLoginUrl(bad,origin),false,bad)
}
assert.equal(validNativeAhLoginUrl(login,'https://example.com'),false)
const frontend=readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx',import.meta.url),'utf8')
assert.match(frontend,/native_http=true/)
assert.match(frontend,/openNativeAhLogin\(data.login_url\)/)
const native=readFileSync(new URL('../../packaging/mobile-inhuis-app/app.mjs',import.meta.url),'utf8')
assert.match(native,/handleInhuisAhStart/)
assert.match(native,/nativeAhReturn/)
console.log('Native AH existing Tailscale 8011 contracts: OK')
