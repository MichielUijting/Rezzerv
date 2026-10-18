import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const header = readFileSync(new URL('../src/ui/Header.jsx', import.meta.url), 'utf8')
assert.match(header, /const \[canSwitchHouseholds, setCanSwitchHouseholds\] = useState\(false\)/)
assert.match(header, /data\?\.can_switch_households === true && items\.length > 1/)
assert.match(header, /\{canSwitchHouseholds && \(/)
assert.match(header, /setCanSwitchHouseholds\(false\)/)

const headerCss = readFileSync(new URL('../src/ui/components/header.css', import.meta.url), 'utf8')
assert.match(header, /className="rz-header-household-select"/)
assert.match(headerCss, /\.rz-header-household-select\s*\{[^}]*background-color:\s*#fff;[^}]*color:\s*#134b2e;/)
assert.match(headerCss, /\.rz-header-household-select option\s*\{[^}]*background-color:\s*#fff;[^}]*color:\s*#134b2e;/)

console.log('HOUSEHOLD_SWITCHER_VISIBILITY_CONTRACT_GREEN')
