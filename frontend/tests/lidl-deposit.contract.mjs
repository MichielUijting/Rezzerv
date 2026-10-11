import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const bridge = readFileSync(new URL('../src/features/storeConnections/lidlWebReceiptBridge.js', import.meta.url), 'utf8')

assert.match(bridge, /lineType:\s*\/\\b\(statiegeld\|deposit\|pfand\)\\b\/i\.test\(description\)\s*\?\s*'deposit'/)
assert.match(bridge, /lineType:\s*'deposit'/)
assert.match(bridge, /product\.lineType\s*!==\s*'deposit'/)
assert.match(bridge, /product\.lineType\s*===\s*'deposit'/)

console.log('Lidl structured deposit classification contract passed')
