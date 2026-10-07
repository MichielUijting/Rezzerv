import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const header = readFileSync(new URL('../src/ui/Header.jsx', import.meta.url), 'utf8')
assert.match(header, /const \[canSwitchHouseholds, setCanSwitchHouseholds\] = useState\(false\)/)
assert.match(header, /data\?\.can_switch_households === true && items\.length > 1/)
assert.match(header, /\{canSwitchHouseholds && \(/)
assert.match(header, /setCanSwitchHouseholds\(false\)/)

console.log('HOUSEHOLD_SWITCHER_VISIBILITY_CONTRACT_GREEN')
