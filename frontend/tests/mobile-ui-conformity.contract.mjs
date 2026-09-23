import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const mobileInventorySource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const mobileInventoryCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const mobileComponentsCss = readFileSync(new URL('../src/ui/mobileComponents.css', import.meta.url), 'utf8')
const themeCss = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')

// Sole visual conformance authority for mobile roots already migrated to the
// new PO-approved design. Functional mobile contracts remain separate.
const MIGRATED_MOBILE_UI = Object.freeze(['voorraad'])
assert.deepEqual(MIGRATED_MOBILE_UI, ['voorraad'])

assert.match(mobileInventorySource, /data-testid="mobile-inventory-page"/)
assert.match(mobileInventorySource, /<MobileModuleHeader title="Voorraad" testId="mobile-inventory-header" \/>/)
assert.match(mobileInventorySource, /selectRecentActionTiles/)
assert.match(mobileInventorySource, /excludeKeys: \['voorraad'\]/)
assert.match(mobileInventorySource, /<QuantityStepper/)
assert.match(mobileInventorySource, /MORE_NAV_ITEM = \{ key: 'meer', label: 'Meer', route: '\/home'/)
assert.match(mobileInventorySource, /\{ value: 'name-asc', label: 'Naam A–Z' \}/)
assert.match(mobileInventorySource, /\{ value: 'name-desc', label: 'Naam Z–A' \}/)
assert.doesNotMatch(mobileInventorySource, /Aantal hoog–laag/)

assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-screen\s*\{[\s\S]*url\('\/inhuis-green-wallpaper\.svg'\)[\s\S]*background-color:\s*#EEF7F0/i,
)
assert.doesNotMatch(mobileInventoryCss, /backdrop-filter/)
assert.doesNotMatch(mobileInventoryCss, /#006b3c|#005630/i)
assert.match(
  mobileComponentsCss,
  /\.rz-mobile-module-header\s*\{[\s\S]*background:\s*var\(--color-mobile-ui-primary\);/,
)
assert.match(
  mobileComponentsCss,
  /\.rz-mobile-module-header-logo\s*\{[\s\S]*height:\s*46px;/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-list\s*\{[\s\S]*background:\s*#ffffff;/i,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-card\s*\{[\s\S]*border-bottom:\s*1px solid #edf0ee;[\s\S]*background:\s*#ffffff;/i,
)
assert.match(
  mobileComponentsCss,
  /\.rz-mobile-action-bar\s*\{[\s\S]*position:\s*fixed;[\s\S]*grid-template-columns:\s*repeat\(var\(--rz-mobile-action-count, 5\), minmax\(0, 1fr\)\);/,
)
assert.match(
  mobileComponentsCss,
  /\.rz-quantity-stepper-button\s*\{[\s\S]*border:\s*1px solid var\(--color-mobile-ui-primary\);[\s\S]*color:\s*var\(--color-mobile-ui-primary\);/,
)

assert.match(
  mobileComponentsCss,
  /\.rz-quantity-stepper-button\s*\{[\s\S]*width:\s*44px;[\s\S]*height:\s*44px;/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-card-side\s*\{[\s\S]*gap:\s*14px;/,
)

// Mobile Voorraad owns the fixed bottom action bar; passive feedback is an
// overlay and therefore adds bottom padding instead of reserving layout space.
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\) \.rz-app-feedback-bar-base,[\s\S]*display:\s*none\s*!important;/,
)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\)[\s\S]*padding-bottom:\s*calc\(70px \+ env\(safe-area-inset-bottom\)\)\s*!important;/,
)

assert.doesNotMatch(mobileInventoryCss, /rz-mobile-inventory-quick-feedback|rz-mobile-inventory-topbar|rz-mobile-inventory-bottom-nav/)

console.log('MOBILE_UI_CONFORMITY_GREEN')
