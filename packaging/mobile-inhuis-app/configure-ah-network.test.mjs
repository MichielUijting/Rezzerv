import assert from 'node:assert/strict'
import { ahNetworkXml, patchAndroidManifest } from './configure-ah-network.mjs'
const manifest='<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:allowBackup="true" android:usesCleartextTraffic="true" /></manifest>'
const patched=patchAndroidManifest(manifest)
assert.match(patched, /android:networkSecurityConfig="@xml\/inhuis_ah_test_network"/)
assert.match(patched, /android:usesCleartextTraffic="false"/)
assert.match(ahNetworkXml, /cleartextTrafficPermitted="true"/)
assert.match(ahNetworkXml, /<domain includeSubdomains="true">ts.net<\/domain>/)
assert.doesNotMatch(ahNetworkXml, /<base-config/)
assert.throws(()=>patchAndroidManifest(patched),/Bestaande Android-netwerkconfiguratie/)
console.log('Android AH Tailscale network configuration contracts: OK')
