import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
// No Android cleartext exceptions or TLS bypass.
export function enforceHttpsOnlyManifest(value) {
  if (!/<application\b/.test(value) || !/xmlns:android=/.test(value)) throw Error('Ongeldig AndroidManifest.xml')
  if (/android:networkSecurityConfig=/.test(value)) throw Error('Netwerkuitzondering: veilig gestopt')
  if (/android:usesCleartextTraffic="(?:true|false)"/.test(value))
    return value.replace(/android:usesCleartextTraffic="(?:true|false)"/, 'android:usesCleartextTraffic="false"')
  return value.replace(/<application\b/, '<application android:usesCleartextTraffic="false"')
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const path = 'android/app/src/main/AndroidManifest.xml'
  const secured = enforceHttpsOnlyManifest(await readFile(path, 'utf8'))
  if (!/android:usesCleartextTraffic="false"/.test(secured)) throw Error('HTTPS-only controle mislukt')
  await writeFile(path, secured)
  console.log('Android cleartext-verkeer geblokkeerd.')
}
