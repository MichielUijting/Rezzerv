import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('../src/features/kassa/KassaPage.jsx', import.meta.url), 'utf8')

assert.match(source, /\/api\/receipts\/retailers\/ah\/status/)
assert.match(source, /\/api\/receipts\/retailers\/ah\/sync/)
assert.match(source, /limit:\s*100/)
assert.match(source, /receipts_processed/)
assert.match(source, /setSyncRevision/)
assert.match(source, /catch\s*\{/)

console.log('AH_AUTO_SYNC_CONTRACT_GREEN')
