import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const appShell = read('src/app/AppShell.jsx')
const table = read('src/ui/Table.jsx')
const settingsPage = read('src/features/settings/SettingsPage.jsx')
const mobileCss = read('src/features/settings/settingsMobile.css')
const main = read('src/main.jsx')

assert.match(appShell, /pathname\.startsWith\('\/instellingen\/'\)/)
assert.match(appShell, /rz-settings-shell/)
assert.match(table, /dataset\.mobileLabel/)
assert.match(settingsPage, /rz-settings-page/)
assert.match(settingsPage, /rz-settings-tile/)
assert.doesNotMatch(settingsPage, /<h2[^>]*>Instellingen<\/h2>/)
assert.match(settingsPage, /rz-settings-section-heading/)
assert.match(settingsPage, /rz-settings-tile-icon/)
assert.match(settingsPage, /rz-settings-tile-chevron/)
assert.match(main, /features\/settings\/settingsMobile\.css/)
assert.match(mobileCss, /@media \(max-width: 720px\)/)
assert.match(mobileCss, /\.rz-settings-shell \.rz-table colgroup,[\s\S]*\.rz-settings-shell \.rz-table thead[\s\S]*display: none/)
assert.match(mobileCss, /content: attr\(data-mobile-label\)/)
assert.match(mobileCss, /grid-template-columns: minmax\(92px, 34%\) minmax\(0, 1fr\)/)
assert.match(mobileCss, /min-height: 44px/)
assert.match(mobileCss, /settings-section-household/)
assert.match(mobileCss, /settings-section-usage/)
assert.match(mobileCss, /settings-section-help/)
assert.match(mobileCss, /--rz-settings-section-tint/)
assert.doesNotMatch(mobileCss, /@media \(min-width:/)

console.log('MOBILE_SETTINGS_CONTRACT_GREEN')
