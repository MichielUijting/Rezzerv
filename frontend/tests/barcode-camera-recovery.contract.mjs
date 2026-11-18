import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import {
  diagnoseBarcodeCameraFailure,
  shouldStopCameraRetries,
} from '../src/lib/barcodeCameraRecovery.js'

function diagnosis(name, opts = {}) {
  return diagnoseBarcodeCameraFailure({ name }, opts)
}
const denied = diagnosis('NotAllowedError', { userAgent: 'Mozilla Firefox Windows' })
assert.equal(denied.reason, 'permission')
assert.equal(denied.canTryCompatibility, false)
assert.match(denied.advice, /Firefox/)
assert.match(denied.deviceAdvice, /Windows/)
assert.equal(shouldStopCameraRetries({ name: 'NotAllowedError' }), true)
assert.equal(shouldStopCameraRetries({ name: 'NotReadableError' }), false)
assert.equal(diagnosis('SecurityError', { secureContext: false }).canTryCompatibility, false)
assert.equal(diagnosis('NotFoundError').reason, 'no_device')
assert.equal(diagnosis('NotReadableError').canTryCompatibility, true)
assert.equal(diagnosis('OverconstrainedError').canTryCompatibility, true)
assert.equal(diagnosis('UnknownError').reason, 'unknown')

const source = readFileSync(fileURLToPath(new URL('../src/lib/barcodeScanner.js', import.meta.url)), 'utf8')
const first = source.indexOf('export async function openBarcodeCameraStream(')
const last = source.indexOf('\n\nexport function createBarcodeReader(', first)
assert.ok(first >= 0 && last > first, 'Shared camera-open implementation not found')
const scannerFn = source.slice(first, last).replace(/^export /, '')
const env = {
  isMobileBrowser: () => false,
  listBarcodeVideoDevices: async () => [{ deviceId: 'cam1', label: 'Webcam' }],
  scoreDeviceLabel: () => 0,
  buildScanVideoConstraints: (extra = {}) => ({
    width: { ideal: 2560 }, height: { ideal: 1440 }, ...extra,
  }),
  shouldStopCameraRetries,
  console: { info() {}, warn() {} },
}
vm.runInNewContext(scannerFn + '\nthis.cameraOpen = openBarcodeCameraStream;', env)

function fakeStream() {
  const track = {
    label: 'Webcam',
    stopCalls: 0,
    stop() { this.stopCalls++ },
    getSettings() { return { deviceId: 'cam1' } },
    getCapabilities() { return { focusMode: ['continuous'] } },
    async applyConstraints() { throw new Error('Compatibility mode must not change track focus') },
  }
  return { stream: { getVideoTracks: () => [track], getTracks: () => [track] }, track }
}

const { stream, track } = fakeStream()
let calls = []
env.navigator = { mediaDevices: { getUserMedia: async (constraints) => {
  calls.push(constraints)
  assert.equal(constraints.audio, false)
  assert.equal(constraints.video, true, 'Explicit compatibility mode must first ask for basic camera')
  return stream
} } }
const compatibility = await env.cameraOpen('', null, { compatibilityMode: true })
assert.equal(calls.length, 1)
assert.equal(compatibility.stream, stream)
assert.equal(compatibility.activeDeviceId, 'cam1')
assert.equal(track.stopCalls, 0)
compatibility.stream.getTracks().forEach(t => t.stop())
assert.equal(track.stopCalls, 1, 'Scanner close must release the temporary track')

calls = []
env.navigator = { mediaDevices: { getUserMedia: async (constraints) => {
  calls.push(constraints)
  throw Object.assign(new Error('permission denied'), { name: 'NotAllowedError' })
} } }
await assert.rejects(env.cameraOpen('', null), { name: 'NotAllowedError' })
assert.equal(calls.length, 1, 'No retry loop is allowed after refusal of camera permission')

const hook = readFileSync(fileURLToPath(new URL('../src/lib/useBarcodeScanner.js', import.meta.url)), 'utf8')
assert.match(hook, /requestTokenRef\.current \+= 1/, 'Closing must invalidate pending access requests')
assert.match(hook, /stream\.getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/,
  'A stream granted after close must be stopped')
assert.match(hook, /startCompatibleCamera.*compatibilityMode: true/)
const modal = readFileSync(fileURLToPath(new URL('../src/features/barcodes/BarcodeScannerModal.jsx', import.meta.url)), 'utf8')
assert.match(modal, /barcode-camera-temporary-consent/)
assert.match(modal, /onPrimaryAction: \(\) => \{ onTryCompatibility\(\); return true \}/)
assert.match(modal, /privacyinstellingen van je laptop of browser niet zelf aanpassen/)
const article = readFileSync(fileURLToPath(new URL('../src/features/barcodes/ArticleBarcodeScanAction.jsx', import.meta.url)), 'utf8')
assert.match(article, /onTryCompatibility=\{\(\) => void startCompatibleCamera\(\)\}/)
assert.match(article, /ArticleBarcodeScanAction/)
assert.doesNotMatch(article, /cameraErrorRevision|ed2-barcode-scanner-message/,
  'Article scanner must not display multiple camera error overlays')
console.log('BARCODE_CAMERA_CONSENT_RECOVERY_GREEN')
