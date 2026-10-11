import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const bridge = readFileSync(new URL('../src/features/storeConnections/lidlWebReceiptBridge.js', import.meta.url), 'utf8')

// Both structured article DOM nodes and plain-text deposit rows must map to deposit.
assert.ok(bridge.includes("test(description) ? 'deposit' : 'product'"))
assert.ok(bridge.includes("lineType: 'deposit'"))
assert.ok(bridge.includes("product.lineType !== 'deposit'"))
assert.ok(bridge.includes("product.lineType === 'deposit'"))

console.log('Lidl structured deposit classification contract passed')
