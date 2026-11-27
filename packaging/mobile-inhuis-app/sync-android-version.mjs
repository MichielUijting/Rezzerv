import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve, dirname, join } from 'node:path'

export function androidVersionCode(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(version || ''))
  if (!match) throw Error('Ongeldige canonieke Android-packageversie')
  const [major, minor, patch] = match.slice(1).map(Number)
  if (major < 0 || major > 2000 || minor > 99 || patch > 9999) {
    throw Error('Android-versie past niet in de toegewezen versionCode-posities')
  }
  const code = major * 1000000 + minor * 10000 + patch
  if (!Number.isSafeInteger(code) || code < 1 || code > 2100000000) {
    throw Error('Android-versionCode valt buiten toegestaan bereik')
  }
  return code
}

export function synchronizeAndroidGradle(source, version) {
  const text = String(source || '')
  const names = [...text.matchAll(/^(\s*)versionName\s+(['"])[^'"\r\n]*\2\s*$/gm)]
  const codes = [...text.matchAll(/^(\s*)versionCode\s+\d+\s*$/gm)]
  if (names.length !== 1 || codes.length !== 1) {
    throw Error('Android Gradle-template wijkt af; versiesynchronisatie veilig gestopt')
  }
  const code = androidVersionCode(version)
  return text.replace(/^(\s*)versionName\s+(['"])[^'"\r\n]*\2(\s*)$/m,
    (_, indent, quote, space) => indent + 'versionName ' + quote + version + quote + space)
    .replace(/^(\s*)versionCode\s+\d+(\s*)$/m,
      (_, indent, space) => indent + 'versionCode ' + code + space)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = dirname(fileURLToPath(import.meta.url))
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  if (typeof pkg.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(pkg.version)) {
    throw Error('Android-package.json heeft geen geldige versie')
  }
  const path = join(root, 'android', 'app', 'build.gradle')
  const original = readFileSync(path, 'utf8')
  const updated = synchronizeAndroidGradle(original, pkg.version)
  if (updated === original) throw Error('Android-versiesynchronisatie heeft geen effect')
  writeFileSync(path, updated)
  console.log('Inhuis Android-versie: ' + pkg.version + ' (versionCode ' + androidVersionCode(pkg.version) + ')')
}
