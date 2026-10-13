import assert from 'node:assert/strict'
import fs from 'node:fs'
import { validateAldiDigitalFile, importAldiDigitalFile, ALDI_DIGITAL_MAX_BYTES } from '../src/features/storeConnections/aldiDigitalReceiptImport.js'

const makeFile = (name, body) => new File([body], name, { type: 'message/rfc822' })
const source = makeFile('shop-go.eml', 'From: shopgo@example.test\nSubject: Bon\n\nSynthetische test.')
assert.equal(validateAldiDigitalFile(source).extension, 'eml')
assert.equal(validateAldiDigitalFile(makeFile('receipt.PDF', 'test')).extension, 'pdf')
assert.throws(() => validateAldiDigitalFile(makeFile('receipt.exe', 'test')))
assert.throws(() => validateAldiDigitalFile(makeFile('receipt.eml', '')))
assert.throws(() => validateAldiDigitalFile({ name: 'big.pdf', size: ALDI_DIGITAL_MAX_BYTES + 1 }))
let calls = 0
const imported = await importAldiDigitalFile(source, 'household-test', async (url, init) => {
  calls++
  assert.equal(url, '/api/receipts/import')
  assert.equal(init.method, 'POST')
  assert.equal(init.credentials, 'include')
  assert.equal(init.body.get('household_id'), 'household-test')
  assert.equal(init.body.get('file').name, source.name)
  assert.equal(init.headers, undefined)
  return { ok: true, json: async () => ({ raw_receipt_id: 'raw-test', duplicate: false }) }
})
assert.equal(calls, 1)
assert.equal(imported.raw_receipt_id, 'raw-test')
await assert.rejects(() => importAldiDigitalFile(source, '', async () => {
  throw Error('must not send')
}))
await assert.rejects(() => importAldiDigitalFile(source, 'household-test', async () => ({
  ok: false, json: async () => ({ detail: 'Ongeldige bon' }),
})), /Ongeldige bon/)
await assert.rejects(() => importAldiDigitalFile(source, 'household-test', async () => ({
  ok: true, json: async () => null,
})), /geen herkenbaar/)
const ui = fs.readFileSync(new URL('../src/features/storeConnections/StoreConnectionsPage.jsx', import.meta.url), 'utf8')
assert.match(ui, /aldi-digital-receipts/)
assert.match(ui, /aldi-digital-file/)
assert.match(ui, /aldi-digital-import/)
assert.match(ui, /importAldiDigitalFile\(/)
assert.match(ui, /\.eml,\.pdf/)
assert.doesNotMatch(ui, /AldiOAuth|AldiGraphQL|aldi_session_token/)
console.log('ALDI_SHOP_GO_SAFE_UPLOAD_CONTRACT_GREEN')
