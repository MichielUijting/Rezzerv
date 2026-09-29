import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/features/settings/SettingsLocationsManagementPage.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/features/settings/settingsLocationsMobile.css', import.meta.url), 'utf8')
assert.match(page, /data-testid="mobile-location-add"/)
assert.match(page, /onSubmit=\{\(event\) => \{ event\.preventDefault\(\); if \(!isSaving\) addLocation\(\) \}\}/)
assert.match(page, /id="mobile-new-main-location"/)
assert.match(page, /Locatie toevoegen/)
assert.match(page, /data-testid="new-main-location-row" className="rz-desktop-location-add"/)
assert.match(page, /isHouseholdAdminFromContext/)
assert.match(page, /fetchJsonWithAuth\('\/api\/spaces', \{/)
assert.match(css, /@media \(max-width: 720px\)/)
assert.match(css, /\.rz-desktop-location-add \{ display: none !important; \}/)
console.log('MOBILE_LOCATION_ADD_CONTRACT_GREEN')
