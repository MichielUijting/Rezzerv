import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { acceptsNativeLidlMessage, startNativeLidlTransport } from '../src/features/storeConnections/nativeLidlTransport.js'
const channel = '91c02527-624d-4fe9-a181-75a5a774c7cd'
const nonce = '48cf6232-c930-4c90-9dbb-3c49b5c6fda4'
const requestId = 'b2766412-f716-4b33-a154-7491b2650480'
const relay = { detail: { channel, nonce, kind: 'inhuis-native-lidl-relay',
  data: { type: 'inhuis:lidl-handshake', request_id: requestId, bookmarklet_version: 2 } } }
assert.equal(acceptsNativeLidlMessage(relay, channel, nonce), true)
assert.equal(acceptsNativeLidlMessage(relay, channel, 'other'), false)
assert.equal(acceptsNativeLidlMessage(relay, channel, nonce, 'another'), false)
assert.equal(acceptsNativeLidlMessage({ detail: { ...relay.detail, channel: 'other' } }, channel, nonce), false)
assert.equal(acceptsNativeLidlMessage({ detail: { ...relay.detail, data: { type: 'unsafe', request_id: requestId } } }, channel, nonce), false)
assert.equal(startNativeLidlTransport({}), null)
const src = readFileSync(new URL('../src/features/storeConnections/nativeLidlTransport.js', import.meta.url), 'utf8')
assert.match(src, /inhuis-native-lidl-start', binding: boundContext/)
assert.match(src, /AUTH_CONTEXT_CHANGED_EVENT/)
assert.match(src, /jumboImportContextMatches/)
console.log('Native Lidl transport contracts: OK')
