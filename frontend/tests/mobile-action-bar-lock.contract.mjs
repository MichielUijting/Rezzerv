import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const chrome = readFileSync(new URL('../src/app/MobileAppChrome.jsx', import.meta.url), 'utf8')
const availability = readFileSync(new URL('../src/features/platform/actionButtonAvailability.js', import.meta.url), 'utf8')
const superuser = readFileSync(new URL('../src/features/superuser/SuperuserActionButtonsSection.jsx', import.meta.url), 'utf8')

assert.match(chrome, /DEFAULT_FIXED_ACTION_BAR_KEYS = Object\.freeze\(\['winkelen', 'kassa', 'kassabonnen', 'voorraad'\]\)/)
assert.match(chrome, /if \(actionAvailability\.actionBarLocked\)/)
assert.match(chrome, /fixedKeys\.map\(\(key\) => byKey\.get\(key\)\)\.filter\(Boolean\)\.slice\(0, 4\)/)
assert.match(chrome, /return \[\.\.\.selected, MORE_NAV_ITEM\]/)

assert.match(availability, /\/api\/platform\/mobile-action-bar/)
assert.match(availability, /actionBarLocked: Boolean\(actionBarPayload\?\.locked\)/)
assert.match(availability, /fixedActionBarKeys/)
assert.match(availability, /\['winkelen', 'kassa', 'kassabonnen', 'voorraad'\]/)

assert.match(superuser, /Actiebalk vastzetten/)
assert.match(superuser, /<option value="yes">Ja<\/option>/)
assert.match(superuser, /<option value="no">Nee<\/option>/)
assert.match(superuser, /\/api\/superuser\/mobile-action-bar/)
assert.match(superuser, /Winkelen, Kassa, Uitpakken en Voorraad/)
assert.match(superuser, /Alle overige beschikbare acties staan onder Meer/)

console.log('MOBILE_ACTION_BAR_LOCK_CONTRACT_GREEN')
