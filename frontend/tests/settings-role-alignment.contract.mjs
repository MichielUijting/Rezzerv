import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const settingsSource = readFileSync(new URL('../src/features/settings/SettingsPage.jsx', import.meta.url), 'utf8')
const householdSource = readFileSync(new URL('../src/features/settings/SettingsHouseholdPage.jsx', import.meta.url), 'utf8')
const authorizationSource = readFileSync(new URL('../src/features/settings/SettingsAuthorizationPage.jsx', import.meta.url), 'utf8')
const membershipServiceSource = readFileSync(new URL('../../backend/app/services/authorization_membership_service.py', import.meta.url), 'utf8')
const membershipRoutesSource = readFileSync(new URL('../../backend/app/api/authorization_membership_routes.py', import.meta.url), 'utf8')

assert.match(
  settingsSource,
  /permission="household_settings\.manage" to="\/instellingen\/winkelimport"/,
  'Winkelimport moet household_settings.manage gebruiken',
)
assert.doesNotMatch(
  settingsSource,
  /permission="catalog\.manage" to="\/instellingen\/winkelimport"/,
  'Winkelimport mag niet catalog.manage gebruiken',
)
assert.match(
  settingsSource,
  /permission="household_settings\.manage" to="\/instellingen\/bijna-op-voorspelling"/,
  'Bijna-op-instellingen moeten household_settings.manage gebruiken',
)
assert.doesNotMatch(
  settingsSource,
  /permission="almost_out\.update" to="\/instellingen\/bijna-op-voorspelling"/,
  'Bijna-op-instellingen mogen niet almost_out.update gebruiken',
)

assert.match(
  householdSource,
  /const ASSIGNABLE_ROLE_KEYS = new Set\(\['household\.member', 'household\.admin'\]\)/,
  'De huishoudrolkeuze moet uitsluitend Lid en Beheerder toewijsbaar maken',
)
for (const [roleKey, label] of [
  ['household.viewer', 'Kijker (bestaande rol)'],
  ['household.advanced_member', 'Geavanceerd lid (bestaande rol)'],
  ['household.owner', 'Superuser'],
  ['household.frontteam', 'Frontteamlid'],
]) {
  assert.ok(householdSource.includes(`'${roleKey}': '${label}'`))
}

for (const [roleKey, label] of [
  ['household.member', 'Lid'],
  ['household.admin', 'Beheerder'],
  ['household.owner', 'Superuser'],
  ['household.frontteam', 'Frontteamlid'],
]) {
  assert.ok(authorizationSource.includes(`'${roleKey}': '${label}'`))
}
assert.match(
  authorizationSource,
  /overview\.roles\.filter\(\(role\) => AUTHORIZATION_ROLE_KEYS\.has\(role\.role_key\)\)/,
  'Het autorisatieoverzicht moet uitsluitend canonieke rolprofielen tonen',
)
assert.doesNotMatch(authorizationSource, /'household\.viewer'/)
assert.doesNotMatch(authorizationSource, /'household\.advanced_member'/)

const assignableRolesBlock = membershipServiceSource.match(/allowed_roles = \{([\s\S]*?)\n    \}/)?.[1] || ''
assert.match(assignableRolesBlock, /"household\.member"/)
assert.match(assignableRolesBlock, /"household\.admin"/)
assert.doesNotMatch(assignableRolesBlock, /household\.(viewer|advanced_member|owner|frontteam)/)

const canonicalRoleQuery = membershipRoutesSource.match(/SELECT role_key,([\s\S]*?)\n        """\)\)\.mappings\(\)\.all\(\)/)?.[1] || ''
for (const roleKey of [
  'household.member',
  'household.admin',
  'household.owner',
  'household.frontteam',
]) {
  assert.ok(canonicalRoleQuery.includes(`'${roleKey}'`))
}
assert.doesNotMatch(canonicalRoleQuery, /household\.(viewer|advanced_member)/)

console.log('SETTINGS_ROLE_ALIGNMENT_CONTRACT_GREEN')
