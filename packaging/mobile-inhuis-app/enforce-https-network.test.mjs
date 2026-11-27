import assert from 'node:assert/strict'
import { enforceHttpsOnlyManifest } from './enforce-https-network.mjs'
const manifest='<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:usesCleartextTraffic="true" /></manifest>'
const secured=enforceHttpsOnlyManifest(manifest)
assert.match(secured,/android:usesCleartextTraffic="false"/)
assert.equal(enforceHttpsOnlyManifest(secured),secured)
assert.match(enforceHttpsOnlyManifest(manifest.replace(' android:usesCleartextTraffic="true"','')),/android:usesCleartextTraffic="false"/)
assert.throws(()=>enforceHttpsOnlyManifest(manifest.replace('<application ','<application android:networkSecurityConfig="@xml/unsafe" ')),/Netwerkuitzondering/)
console.log('Android HTTPS-only manifest contracts: OK')
