import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const preference = readFileSync(new URL('../src/ui/fontScalePreference.js', import.meta.url), 'utf8')
const main = readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('../src/features/settings/SettingsPage.jsx', import.meta.url), 'utf8')
const tokens = readFileSync(new URL('../src/ui/tokens.css', import.meta.url), 'utf8')

assert.match(tokens, /--font-size-ui-body:\s*14px/)
assert.match(tokens, /--font-size-ui-title:\s*16px/)
assert.match(preference, /standard:\s*\{[^}]*body:\s*'14px'[^}]*title:\s*'16px'/)
assert.match(preference, /large:\s*\{[^}]*body:\s*'17px'[^}]*title:\s*'20px'/)
assert.match(preference, /extraLarge:\s*\{[^}]*body:\s*'20px'[^}]*title:\s*'24px'/)
assert.match(preference, /--font-size-ui-body/)
assert.match(preference, /--font-size-ui-title/)
assert.match(preference, /localStorage/)
assert.match(main, /initializeFontScalePreference\(\)/)
assert.match(settings, /data-testid="settings-font-scale"/)
assert.match(settings, /settings-font-scale-standard/)
assert.match(settings, /settings-font-scale-large/)
assert.match(settings, /settings-font-scale-extraLarge/)
assert.match(settings, /Browser- en systeemzoom blijven daarnaast beschikbaar/)

console.log('ACCESSIBLE_FONT_SCALE_GREEN')
