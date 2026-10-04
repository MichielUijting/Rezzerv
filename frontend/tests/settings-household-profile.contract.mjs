import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { getSettingsTile } from '../src/features/settings/settingsNavigation.js'

const page = readFileSync(new URL('../src/features/settings/SettingsHouseholdProfilePage.jsx', import.meta.url), 'utf8')
const account = readFileSync(new URL('../src/features/settings/SettingsMyAccountPage.jsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('../src/features/settings/SettingsPage.jsx', import.meta.url), 'utf8')
const router = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const superuser = readFileSync(new URL('../src/features/superuser/SuperuserControlPage.jsx', import.meta.url), 'utf8')
const matrix = readFileSync(new URL('../../docs/product/INHUIS-INSTELLINGEN-GEGEVENS-EN-ROLLEN.md', import.meta.url), 'utf8')

const profileTile = getSettingsTile('household-profile')
assert.equal(profileTile?.permission, 'household_settings.view')
assert.deepEqual(profileTile?.allowedContexts, ['regular'])
assert.equal(profileTile?.scope, 'household')

for (const label of [
  'Naam huishouden',
  'Straat',
  'Huisnummer',
  'Postcode',
  'Woonplaats',
  'Voorkeurswinkels',
  'Normaal aantal dagen tussen boodschappen',
  'Standaard reservevoorraad in dagen',
  'Bewoners',
  'Voornaam',
  'Bewonerstype',
  'Geboortedatum',
  'Leeftijdscategorie',
  'Gekoppeld Inhuis-account',
]) {
  assert.ok(page.includes(label), `Huishoudprofiel mist: ${label}`)
}

assert.match(page, /resident_count/)
assert.match(page, /Volwassene/)
assert.match(page, /Kind/)
assert.match(page, /Geen account gekoppeld/)
assert.doesNotMatch(page, /window\.confirm/)
assert.match(page, /household-resident-remove-modal/)

assert.match(account, /label="Naam"/)
assert.match(account, /\/api\/account\/profile/)
assert.match(router, /path: '\/instellingen\/huishoudprofiel'/)
assert.match(router, /path: '\/instellingen\/frontteam'.*ProtectedSuperuser/)
assert.equal(getSettingsTile('frontteam'), null)

assert.match(superuser, /'Frontteam'/)
assert.match(superuser, /SettingsFrontteamPage/)
assert.match(superuser, /'Weergave'/)
assert.match(superuser, /SuperuserAppearanceSection/)
assert.doesNotMatch(settings, /settings-primary-color-picker/)
assert.doesNotMatch(settings, /rz-settings-tile-chevron|›/)

for (const sensitive of ['Allergieën', 'medische beperkingen', 'gezondheidsprofielen']) {
  assert.ok(matrix.includes(sensitive), `Privacygrens mist: ${sensitive}`)
}
assert.match(matrix, /niet.*standaard/i)
assert.match(matrix, /bewoner.*niet hetzelfde.*Inhuis-gebruiker/i)

console.log('SETTINGS_HOUSEHOLD_PROFILE_CONTRACT_GREEN')
