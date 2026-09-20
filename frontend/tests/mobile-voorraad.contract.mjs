import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import {
  MOBILE_INVENTORY_MEDIA_QUERY,
  isMobileInventoryEligibleContext,
  isMobileInventoryViewport,
} from '../src/pages/mobileInventoryAccess.js'

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
const mobileCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const orangeWallpaper = new URL('../public/inhuis-orange-wallpaper.svg', import.meta.url)

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
assert.match(mobileSource, /data-testid="mobile-inventory-add-incidental-purchase"/)
assert.match(mobileSource, /data-testid="mobile-inventory-location-filter"/)
assert.match(mobileSource, /locationTrackingEnabled \? 'Zoek artikel, groep of locatie' : 'Zoek artikel of groep'/)
assert.match(mobileSource, /\.\.\.\(locationTrackingEnabled \? \[\{ value: 'location', label: 'Locatie A–Z' \}\] : \[\]\)/)
assert.match(mobileSource, /\/api\/dev\/inventory-preview/)
assert.match(mobileSource, /\/api\/article-groups\/household-articles/)
assert.match(mobileSource, /CatalogArticleThumbnail/)
assert.match(mobileSource, /imageUrl:\s*String\(item\?\.image_url/)
assert.match(mobileSource, /imageUrl=\{row\.imageUrl\}/)

assert.equal(existsSync(orangeWallpaper), true)
assert.match(mobileCss, /\/inhuis-orange-wallpaper\.svg/)
assert.match(mobileCss, /backdrop-filter:\s*blur\(/)
assert.match(mobileCss, /data-location-tracking='disabled'[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\)/)
assert.match(mobileCss, /rz-mobile-inventory-card-meta span:first-child[\s\S]*border-radius:\s*999px/)
assert.match(mobileCss, /rz-mobile-inventory-actions[\s\S]*position:\s*sticky/)
assert.match(mobileCss, /rz-mobile-inventory-summary[\s\S]*background:\s*var\(--color-ui-primary\)[\s\S]*color:\s*var\(--color-ui-primary-text\)/)

console.log('MOBILE_VOORRAAD_CONTRACT_GREEN')
