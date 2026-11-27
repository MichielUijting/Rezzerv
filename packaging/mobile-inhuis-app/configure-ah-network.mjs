import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// This configuration is generated exclusively for the isolated Android test
// app, never for Docker, production applications or arbitrary HTTP domains.
// All actual Inhuis UI/API traffic remains HTTPS.
export const ahNetworkXml = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="true">ts.net</domain>
  </domain-config>
</network-security-config>
`

export function patchAndroidManifest(value) {
  if (!/<application\b/.test(value) || !/xmlns:android=/.test(value)) {
    throw Error('AndroidManifest.xml mist application of namespace')
  }
  if (/android:networkSecurityConfig=/.test(value)) {
    throw Error('Bestaande Android-netwerkconfiguratie: veilig gestopt')
  }
  return value.replace(/<application\b/, '<application android:networkSecurityConfig="@xml/inhuis_ah_test_network"')
    .replace(/android:usesCleartextTraffic="(?:true|false)"/, 'android:usesCleartextTraffic="false"')
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = 'android/app/src/main'
  const manifestPath = root + '/AndroidManifest.xml'
  const manifest = await readFile(manifestPath, 'utf8')
  const patched = patchAndroidManifest(manifest)
  await mkdir(root + '/res/xml', { recursive: true })
  await writeFile(manifestPath, patched)
  await writeFile(root + '/res/xml/inhuis_ah_test_network.xml', ahNetworkXml)
  console.log('AH-testverkeer beperkt tot Tailscale-domeinen via bestaande poort 8011.')
}
