import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

// Exercise the actual service with controlled HTTP responses, without a browser.
const source = readFileSync(new URL('../src/features/settings/services/almostOutSettingsService.js', import.meta.url), 'utf8')
let response
let sent
const context = vm.createContext({
  API_BASE_URL: '',
  getAuthHeaders: () => ({}),
  fetchJsonWithAuth: async (_url, options) => {
    sent = options
    return { ok: response.ok, json: async () => response.body }
  },
})
vm.runInContext(source.replace(/^import .*$/gm, '').replace(/export /g, '') + '\nthis.service = { ALMOST_OUT_POLICY_OPTIONS, saveAlmostOutSettings, fetchAlmostOutSettings }', context)
const service = context.service
assert.equal(service.ALMOST_OUT_POLICY_OPTIONS.length, 2)
assert.equal(service.ALMOST_OUT_POLICY_OPTIONS.map(option => option.value).join(','), 'advisory,override')
for (const option of service.ALMOST_OUT_POLICY_OPTIONS) {
  response = { ok: true, body: { prediction_enabled: true, prediction_days: 7, policy_mode: option.value } }
  const saved = await service.saveAlmostOutSettings({ predictionEnabled: true, predictionDays: 7, policyMode: option.value })
  assert.equal(saved.policyMode, option.value)
  assert.equal(JSON.parse(sent.body).policy_mode, option.value)
  assert.equal(saved.predictionEnabled, true)
}
response = { ok: false, body: { detail: [{ loc: ['body', 'policy_mode'], msg: 'Value error', input: 'private input' }] } }
await assert.rejects(service.saveAlmostOutSettings({}), error => {
  assert.equal(error.message, 'De instellingen zijn niet opgeslagen. Controleer de gekozen instelling en het aantal dagen.')
  assert.doesNotMatch(error.message, /object Object|private input|policy_mode/)
  return true
})
response = { ok: false, body: { detail: 'Je hebt geen rechten om dit te wijzigen.' } }
await assert.rejects(service.saveAlmostOutSettings({}), /Je hebt geen rechten om dit te wijzigen\./)
response = { ok: false, body: { detail: { unexpected: 'private input' } } }
await assert.rejects(service.saveAlmostOutSettings({}), /De instellingen voor Bijna op konden niet worden opgeslagen/)
response = { ok: false, body: {} }
await assert.rejects(service.fetchAlmostOutSettings(), /De instellingen voor Bijna op konden niet worden geladen/)
console.log('ALMOST_OUT_SETTINGS_SAVE_GREEN')
