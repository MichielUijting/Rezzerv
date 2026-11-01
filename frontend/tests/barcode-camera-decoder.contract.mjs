import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const file = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
  '../src/lib/barcodeScanner.js')
const source = fs.readFileSync(file, 'utf8')
const from = source.indexOf('function startProcessedFrameDecoding(')
const to = source.indexOf('\n\nexport function isNonFatalBarcodeScanError(', from)
assert.ok(from >= 0 && to > from, 'Shared processed-frame scanner missing')
const productionFunction = source.slice(from, to)
const ean = '8718452801886'
// EAN-13 checksum, independent of the scanner implementation.
const digits = ean.split('').map(Number)
const checksum = (10 - digits.slice(0, 12)
  .reduce((sum, digit, index) => sum + digit * (index % 2 === 0 ? 1 : 3), 0) % 10) % 10
assert.equal(checksum, digits[12], 'Test EAN must be valid')

const timers = new Map()
let nextId = 1
let decodeCalls = 0
let resetCalls = 0
let captured = []
let unexpectedErrors = []
const frameResult = { getText: () => ean }
const env = {
  document: {
    createElement: (tag) => {
      assert.equal(tag, 'canvas')
      return { getContext: () => ({}) }
    },
  },
  window: {
    setTimeout: (cb, ms) => {
      assert.equal(ms, 260)
      const id = nextId++
      timers.set(id, cb)
      return id
    },
    clearTimeout: (id) => timers.delete(id),
  },
  createProcessedFrameReader: () => ({ reset: () => { resetCalls++ } }),
  createProcessedFrameCandidates: () => [{ name: 'center-wide-normal', imageData: {} }],
  decodeImageDataWithZxing: () => {
    decodeCalls++
    return frameResult
  },
  isNonFatalBarcodeScanError: () => false,
}
vm.runInNewContext(productionFunction
  + '\nthis.startProcessedFrameDecoding = startProcessedFrameDecoding;', env)
const controls = env.startProcessedFrameDecoding({
  video: { readyState: 4, videoWidth: 1280, videoHeight: 720 },
  onAttempt: () => {},
  onResult: (result) => { captured.push(result.getText()) },
  onNonFatalError: (err) => { unexpectedErrors.push(String(err)) },
})
assert.equal(decodeCalls, 0, 'Decoder must wait until controls have initialized')
assert.equal(timers.size, 1, 'Scanner must schedule its first frame')
const [, processFrame] = timers.entries().next().value
timers.clear()
processFrame()
assert.equal(decodeCalls, 1, 'A visible frame must be decoded')
assert.deepEqual(captured, [ean], 'Recognized barcode must reach result callback exactly once')
assert.deepEqual(unexpectedErrors, [], 'A successful scan must not throw or be swallowed')
assert.equal(timers.size, 0, 'No more frames after successful detection')
controls.stop()
assert.ok(resetCalls >= 1, 'Decoder must release resources')
console.log('BARCODE_CAMERA_PROCESSED_FRAME_RESULT_GREEN')
