import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/features/settings/SettingsMyHouseholdsPage.jsx', import.meta.url), 'utf8')
const service = readFileSync(new URL('../src/features/settings/services/householdLifecycleService.js', import.meta.url), 'utf8')
const navigation = readFileSync(new URL('../src/features/settings/settingsNavigation.js', import.meta.url), 'utf8')
const router = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const backend = readFileSync(new URL('../../backend/app/api/session_household_routes.py', import.meta.url), 'utf8')
const lifecycle = readFileSync(new URL('../../backend/app/services/multi_household_lifecycle_service.py', import.meta.url), 'utf8')

assert.match(navigation, /key: 'my-households'/)
assert.match(navigation, /to: '\/instellingen\/mijn-huishoudens'/)
assert.match(router, /SettingsMyHouseholdsPage/)
assert.match(router, /settingKey="my-households"/)

assert.match(page, /Nieuw huishouden maken/)
assert.match(page, /Je wordt Beheerder van het nieuwe huishouden/)
assert.match(page, /Huishouden verwijderen/)
assert.match(page, /VERWIJDER \$\{deleteTarget\.household_id\}/)
assert.match(page, /Verwijderen kan pas wanneer alleen jij als Beheerder overblijft/)

assert.match(service, /POST/)
assert.match(service, /DELETE/)
assert.match(service, /\/api\/session\/households/)

assert.match(backend, /@router\.post\("\/api\/session\/households", status_code=201\)/)
assert.match(backend, /@router\.delete\("\/api\/session\/households\/\{household_id\}"\)/)
assert.match(backend, /"redirect_to": "\/onboarding"/)
assert.match(backend, /"can_create_household": not context\.is_frontteam/)

assert.match(lifecycle, /role_key != "household\.admin"/)
assert.match(lifecycle, /member_count != 1/)
assert.match(lifecycle, /target == str\(active_household_id or ""\)\.strip\(\)/)
assert.match(lifecycle, /expected = f"VERWIJDER \{target\}"/)
assert.match(lifecycle, /start_new_household_onboarding/)
assert.match(lifecycle, /"onboarding_status": onboarding\.onboarding_status/)

console.log('MULTI_HOUSEHOLD_LIFECYCLE_CONTRACT_GREEN')
