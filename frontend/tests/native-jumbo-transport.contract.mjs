import assert from 'node:assert/strict'
import {
  nativeJumboShell, acceptsNativeJumboMessage, startNativeJumboTransport,
} from '../src/features/storeConnections/nativeJumboTransport.js'

const channel = '91c02527-624d-4fe9-a181-75a5a774c7cd'
const nonce = '48cf6232-c930-4c90-9dbb-3c49b5c6fda4'
const relay = { detail: { channel, nonce, kind: 'inhuis-native-jumbo-relay',
  data: { type: 'inhuis:jumbo-handshake', request_id: 'synthetic-request' } } }
assert.equal(nativeJumboShell({}), null)
assert.equal(nativeJumboShell({ __inhuisNativeShell: { version: 1, channel } }), null)
assert.equal(nativeJumboShell({ mobileApp: { postMessage() {} },
  __inhuisNativeShell: { version: 1, channel } }).version, 1)
assert.equal(acceptsNativeJumboMessage(relay, channel, nonce), true)
assert.equal(acceptsNativeJumboMessage(relay, channel, 'other'), false)
assert.equal(acceptsNativeJumboMessage({ detail: { ...relay.detail, channel: 'other' } }, channel, nonce), false)
assert.equal(acceptsNativeJumboMessage({ detail: { ...relay.detail, data: { type: 'unsafe' } } }, channel, nonce), false)
assert.equal(startNativeJumboTransport({}), null)
assert.equal(startNativeJumboTransport({ __inhuisNativeShell: { version: 1, channel },
  mobileApp: { postMessage() {} }, crypto: { randomUUID: () => nonce } }), null)
console.log('Native Jumbo transport checks: OK')
