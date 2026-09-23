import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  MOBILE_INVENTORY_MEDIA_QUERY,
  isMobileInventoryEligibleContext,
  isMobileInventoryViewport,
} from '../src/pages/mobileInventoryAccess.js'
import {
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from '../src/features/home/recentActionUsage.js'

const regularMember = {
  context_type: 'regular',
  role: 'member',
  display_role: 'member',
  permissions: {},
  is_frontteam: false,
  is_platform_superuser: false,
}

const regularAdmin = {
  context_type: 'regular',
  role: 'admin',
  display_role: 'admin',
  permissions: { 'admin.access': true },
  is_frontteam: false,
  is_platform_superuser: false,
}

assert.equal(isMobileInventoryEligibleContext(regularMember), true)
assert.equal(isMobileInventoryEligibleContext(regularAdmin), true)
assert.equal(isMobileInventoryEligibleContext({ ...regularAdmin, display_role: 'beheerder' }), true)
assert.equal(isMobileInventoryEligibleContext({ ...regularAdmin, display_role: 'owner' }), true)

assert.equal(isMobileInventoryEligibleContext({ ...regularMember, display_role: 'viewer', role: 'viewer' }), false)
assert.equal(isMobileInventoryEligibleContext({ ...regularMember, display_role: 'advanced_member', role: 'advanced_member' }), false)

assert.equal(isMobileInventoryEligibleContext({
  ...regularAdmin,
  is_frontteam: true,
}), false)

assert.equal(isMobileInventoryEligibleContext({
  ...regularAdmin,
  permissions: { 'frontteam.external_databases.access': true },
}), false)

assert.equal(isMobileInventoryEligibleContext({
  context_type: 'system',
  role: 'owner',
  display_role: 'owner',
  permissions: { 'platform.system_household.access': true },
  is_platform_superuser: true,
}), false)

assert.equal(isMobileInventoryEligibleContext({
  context_type: 'none',
  role: null,
  display_role: null,
  permissions: { 'platform.feature_flags.manage': true },
}), false)

assert.equal(isMobileInventoryEligibleContext({
  ...regularAdmin,
  permissions: { 'platform.functional_features.manage': true },
}), false)

assert.equal(isMobileInventoryEligibleContext({
  ...regularAdmin,
  permissions: { 'platform.special_roles.manage': true },
}), false)

assert.equal(MOBILE_INVENTORY_MEDIA_QUERY, '(max-width: 720px)')
assert.equal(isMobileInventoryViewport({ matches: true }), true)
assert.equal(isMobileInventoryViewport({ matches: false }), false)
assert.equal(isMobileInventoryViewport(null), false)

const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const selectorSource = readFileSync(new URL('../src/pages/VoorraadResponsive.jsx', import.meta.url), 'utf8')
const selectorCss = readFileSync(new URL('../src/pages/voorraadResponsive.css', import.meta.url), 'utf8')
const mobileSource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const homeSource = readFileSync(new URL('../src/features/home/HomePage.jsx', import.meta.url), 'utf8')

assert.match(routerSource, /import VoorraadResponsive from '\.\.\/\.\.\/pages\/VoorraadResponsive\.jsx'/)
assert.match(routerSource, /path: '\/voorraad'.*<VoorraadResponsive \/>/)
assert.match(selectorSource, /isMobileViewport && isMobileInventoryEligibleContext\(context\)/)
assert.match(selectorSource, /product_configuration\?\.location_tracking_level/)
assert.match(selectorSource, /fetchHouseholdOnboarding\(context, \{ force: true \}\)/)
assert.doesNotMatch(selectorSource, /primary_use_case\s*===\s*['"]waar_inhuis['"]/) 
assert.match(selectorSource, /<MobileVoorraad locationTrackingEnabled=\{locationTrackingEnabled\} \/>/)
assert.match(selectorSource, /data-location-tracking=\{locationTrackingEnabled \? 'enabled' : 'disabled'\}/)
assert.match(selectorSource, /<Voorraad \/>/)
assert.match(selectorCss, /rz-inventory-presentation--locationless[\s\S]*nth-child\(5\)/)
assert.match(selectorCss, /rz-inventory-presentation--locationless[\s\S]*nth-child\(6\)/)

assert.match(mobileSource, /data-testid="mobile-inventory-page"/)
assert.match(mobileSource, /data-testid="mobile-inventory-header"/)
assert.match(mobileSource, /<h1>Voorraad<\/h1>/)
assert.match(mobileSource, /data-testid="mobile-inventory-add-incidental-purchase"/)
assert.match(mobileSource, /data-testid="mobile-inventory-location-filter"/)
assert.match(mobileSource, /data-testid="mobile-inventory-bottom-nav"/)
assert.match(mobileSource, /selectRecentActionTiles/)
assert.match(mobileSource, /readRecentActionKeys\(context\)/)
assert.match(mobileSource, /recordRecentAction\(item\.key, context\)/)
assert.match(mobileSource, /MORE_NAV_ITEM = \{ key: 'meer', label: 'Meer', route: '\/home'/)
assert.match(homeSource, /recordRecentAction\(tile\.key, context\)/)
assert.doesNotMatch(mobileSource, /<Header title="Voorraad"/)
assert.match(mobileSource, /locationTrackingEnabled \? 'Zoek artikel, groep of locatie' : 'Zoek artikel of groep'/)
assert.match(mobileSource, /\{ value: 'name-asc', label: 'Naam A–Z' \}/)
assert.match(mobileSource, /\{ value: 'name-desc', label: 'Naam Z–A' \}/)
assert.doesNotMatch(mobileSource, /Aantal hoog–laag/)
assert.match(mobileSource, /\.\.\.\(locationTrackingEnabled \? \[\{ value: 'location', label: 'Locatie A–Z' \}\] : \[\]\)/)
assert.match(mobileSource, /\/api\/dev\/inventory-preview/)
assert.match(mobileSource, /\/api\/article-groups\/household-articles/)
assert.match(mobileSource, /CatalogArticleThumbnail/)
assert.match(mobileSource, /imageUrl:\s*String\(item\?\.image_url/)
assert.match(mobileSource, /imageUrl=\{row\.imageUrl\}/)



const fakeStorageValues = new Map()
const fakeWindow = {
  localStorage: {
    getItem: (key) => fakeStorageValues.get(key) || null,
    setItem: (key, value) => fakeStorageValues.set(key, value),
  },
}
const recentContext = { user_id: 'user-a' }
recordRecentAction('winkelen', recentContext, fakeWindow)
recordRecentAction('voorraad', recentContext, fakeWindow)
recordRecentAction('kassa', recentContext, fakeWindow)
recordRecentAction('winkelen', recentContext, fakeWindow)
assert.deepEqual(readRecentActionKeys(recentContext, fakeWindow), ['winkelen', 'kassa', 'voorraad'])
assert.deepEqual(readRecentActionKeys({ user_id: 'user-b' }, fakeWindow), [])
assert.deepEqual(
  selectRecentActionTiles({
    recentKeys: ['winkelen', 'kassa', 'voorraad'],
    availableTiles: [
      { key: 'voorraad', label: 'Voorraad', clickable: true },
      { key: 'winkelen', label: 'Boodschappenlijst', clickable: true },
      { key: 'bijna-op', label: 'Bijna op', clickable: true },
    ],
    limit: 4,
  }).map((tile) => tile.key),
  ['winkelen', 'voorraad', 'bijna-op'],
)

console.log('MOBILE_VOORRAAD_CONTRACT_GREEN')
