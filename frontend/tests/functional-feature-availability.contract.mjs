import assert from 'node:assert/strict'
import { buildHomeNavigation } from '../src/features/home/homeNavigation.js'
import { FEATURE_GERECHTEN, isFeatureEnabled } from '../src/features/platform/featureAvailability.js'
import { PLATFORM_NAVIGATION_ITEMS } from '../src/features/platform/platformNavigation.js'

for (const isPlatformSuperuser of [false, true]) {
  const visibility = { isPlatformSuperuser, canOpenAdmin: true, canOpenExternalDatabases: true }
  const build = (features) => buildHomeNavigation({ visibility, features }).primaryTiles
  const off = build({})
  const on = build({ [FEATURE_GERECHTEN]: true })
  assert.ok(!off.some((tile) => tile.key === 'recepten'))
  assert.deepEqual(build({ [FEATURE_GERECHTEN]: false }), off)
  assert.deepEqual(on.filter((tile) => tile.key !== 'recepten'), off)
  assert.equal(on.find((tile) => tile.key === 'recepten').clickable, false)
  for (const value of [undefined, null, 'true', 1, false]) {
    assert.equal(isFeatureEnabled({ [FEATURE_GERECHTEN]: value }, FEATURE_GERECHTEN), false)
  }
}
assert.equal(isFeatureEnabled(Object.create({ [FEATURE_GERECHTEN]: true }), FEATURE_GERECHTEN), false)
assert.equal(PLATFORM_NAVIGATION_ITEMS.find((item) => item.key === 'functional-features').permission,
  'platform.functional_features.manage')
assert.equal(PLATFORM_NAVIGATION_ITEMS.find((item) => item.key === 'feature-flags').permission,
  'platform.feature_flags.manage')
console.log('FUNCTIONAL_FEATURE_AVAILABILITY_CONTRACT_GREEN')
