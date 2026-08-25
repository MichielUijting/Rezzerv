import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  SETTINGS_ROOT_POLICY,
  SETTINGS_SECTIONS,
  SETTINGS_TILES,
  getSettingsTile,
} from '../src/features/settings/settingsNavigation.js'

const settingsPageSource = readFileSync(
  new URL('../src/features/settings/SettingsPage.jsx', import.meta.url),
  'utf8',
)
const settingsGuardSource = readFileSync(
  new URL('../src/app/router/SettingsGuard.jsx', import.meta.url),
  'utf8',
)
const appRouterSource = readFileSync(
  new URL('../src/app/router/AppRouter.jsx', import.meta.url),
  'utf8',
)

assert.deepEqual(
  SETTINGS_SECTIONS.map(({ key, title }) => [key, title]),
  [
    ['account', 'Mijn account'],
    ['household', 'Huishouden & samen gebruiken'],
    ['usage', 'Gebruik & inrichting'],
    ['help', 'Hulp & informatie'],
  ],
  'Settings v2 moet exact de vier canonical informatiesecties definiëren',
)

assert.deepEqual(SETTINGS_ROOT_POLICY.allowedContexts, ['regular'])
assert.equal(SETTINGS_ROOT_POLICY.allowViewer, true)

const expectedTiles = {
  'article-details': { section: 'account', scope: 'personal', permission: null, allowViewer: true },
  'privacy-data-sharing': { section: 'account', scope: 'personal', permission: null, allowViewer: true },
  household: { section: 'household', scope: 'household', permission: 'household_settings.manage', allowViewer: false },
  authorizations: { section: 'household', scope: 'household', permission: null, allowViewer: true },
  capabilities: { section: 'usage', scope: 'household', permission: 'household_settings.manage', allowViewer: false },
  'article-groups': { section: 'usage', scope: 'household', permission: 'article_groups.manage', allowViewer: false },
  locations: { section: 'usage', scope: 'household', permission: 'locations.manage', allowViewer: false },
  'store-import': { section: 'usage', scope: 'household', permission: 'household_settings.manage', allowViewer: false },
  'household-automation': { section: 'usage', scope: 'household', permission: 'household_settings.manage', allowViewer: false },
  'almost-out': { section: 'usage', scope: 'household', permission: 'household_settings.manage', allowViewer: false },
}

assert.equal(SETTINGS_TILES.length, Object.keys(expectedTiles).length)
for (const [key, expected] of Object.entries(expectedTiles)) {
  const tile = getSettingsTile(key)
  assert.ok(tile, `Canonical Settings metadata ontbreekt voor ${key}`)
  assert.equal(tile.section, expected.section)
  assert.equal(tile.scope, expected.scope)
  assert.equal(tile.permission ?? null, expected.permission)
  assert.equal(tile.allowViewer, expected.allowViewer)
  assert.deepEqual(tile.allowedContexts, ['regular'])
}

for (const deferredKey of ['account', 'notifications', 'help', 'about', 'recipes']) {
  assert.equal(
    getSettingsTile(deferredKey),
    null,
    `${deferredKey} mag in 9.3.2 nog geen half-afgebouwde instellingenbestemming worden`,
  )
}

assert.match(settingsPageSource, /navigation\.sections\.map\(\(section\) =>/)
assert.match(settingsPageSource, /settings-section-\$\{section\.key\}/)
assert.match(settingsPageSource, /data-settings-scope=\{tile\.scope\}/)

assert.match(settingsGuardSource, /allowedContexts = \['regular'\]/)
assert.match(settingsGuardSource, /if \(!allowedContexts\.includes\(contextType\)\)/)
assert.match(settingsGuardSource, /<Navigate to="\/home" replace \/>/)

assert.match(appRouterSource, /SETTINGS_ROOT_POLICY, getSettingsTile/)
assert.match(appRouterSource, /function ProtectedSettingsRoute\(/)
assert.match(appRouterSource, /const policy = settingKey \? getSettingsTile\(settingKey\) : SETTINGS_ROOT_POLICY/)
assert.doesNotMatch(appRouterSource, /function ProtectedSettings\(/)

for (const [path, key] of [
  ['/instellingen/mogelijkheden', 'capabilities'],
  ['/instellingen/artikeldetails/veldzichtbaarheid', 'article-details'],
  ['/instellingen/artikelgroepen', 'article-groups'],
  ['/instellingen/privacy-datadeling', 'privacy-data-sharing'],
  ['/instellingen/huishoudautomatisering', 'household-automation'],
  ['/instellingen/bijna-op-voorspelling', 'almost-out'],
  ['/instellingen/winkelimport', 'store-import'],
  ['/instellingen/huishouden', 'household'],
  ['/instellingen/huishouden/autorisaties', 'authorizations'],
  ['/instellingen/locaties', 'locations'],
]) {
  assert.ok(
    appRouterSource.includes(`{ path: '${path}', element: <ProtectedSettingsRoute settingKey="${key}">`),
    `${path} moet zijn directe routegrens uit canonical Settings metadata halen`,
  )
}

for (const legacyPath of ['/instellingen/ruimtes', '/instellingen/sublocaties']) {
  assert.ok(appRouterSource.includes(`{ path: '${legacyPath}', element: <ProtectedSettingsRoute settingKey="locations">`))
}
assert.ok(appRouterSource.includes('<Navigate to="/instellingen/locaties" replace />'))

console.log('SETTINGS_V2_INFORMATION_ARCHITECTURE_CONTRACT_GREEN')