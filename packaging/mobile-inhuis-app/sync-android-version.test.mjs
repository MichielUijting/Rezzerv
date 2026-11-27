import assert from 'node:assert/strict'
import test from 'node:test'
import { androidVersionCode, synchronizeAndroidGradle } from './sync-android-version.mjs'

test('Android versionName and versionCode match canonical Inhuis package version', () => {
  const sample = 'android {\n defaultConfig {\n    applicationId "nl.inhuis.androidtest"\n    versionCode 1\n    versionName "1.0"\n }\n}\n'
  const result = synchronizeAndroidGradle(sample, '1.12.459')
  assert.match(result, /versionCode 1120459/)
  assert.match(result, /versionName "1\.12\.459"/)
  assert.ok(!result.includes('versionName "1.0"'))
  assert.equal(androidVersionCode('1.12.459'), 1120459)
  assert.equal(androidVersionCode('1.12.460'), 1120460)
})
test('Android version synchronization fails closed on changed Gradle template', () => {
  assert.throws(() => synchronizeAndroidGradle('versionName "1.0"', '1.12.459'), /veilig gestopt/)
  assert.throws(() => synchronizeAndroidGradle('versionCode 1', '1.12.459'), /veilig gestopt/)
  assert.throws(() => androidVersionCode('bad'), /Ongeldige/)
})
