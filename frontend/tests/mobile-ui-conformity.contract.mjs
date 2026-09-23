import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const mobileInventorySource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const mobileInventoryCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const themeCss = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')

// Sole visual conformance authority for mobile roots already migrated to the
// new PO-approved design. Functional mobile contracts remain separate.
const MIGRATED_MOBILE_UI = Object.freeze(['voorraad'])
assert.deepEqual(MIGRATED_MOBILE_UI, ['voorraad'])

assert.match(mobileInventorySource, /data-testid="mobile-inventory-page"/)
assert.match(mobileInventorySource, /data-testid="mobile-inventory-header"/)
assert.match(mobileInventorySource, /<h1>Voorraad<\/h1>/)
assert.match(mobileInventorySource, /src="\/inhuis-logo-white\.png"/)
assert.match(mobileInventorySource, /selectRecentActionTiles/)
assert.match(mobileInventorySource, /MORE_NAV_ITEM = \{ key: 'meer', label: 'Meer', route: '\/home'/)
assert.match(mobileInventorySource, /\{ value: 'name-asc', label: 'Naam A–Z' \}/)
assert.match(mobileInventorySource, /\{ value: 'name-desc', label: 'Naam Z–A' \}/)
assert.doesNotMatch(mobileInventorySource, /Aantal hoog–laag/)

assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-screen\s*\{[\s\S]*url\('\/inhuis-green-wallpaper\.svg'\)[\s\S]*background-color:\s*#EEF7F0/i,
)
assert.doesNotMatch(mobileInventoryCss, /backdrop-filter/)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-topbar\s*\{[\s\S]*justify-content:\s*space-between;[\s\S]*background:\s*var\(--color-ui-primary\);/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-topbar h1\s*\{[\s\S]*color:\s*var\(--color-ui-primary-text\);/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-header-logo\s*\{[\s\S]*height:\s*46px;/,
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
  mobileInventoryCss,
  /\.rz-mobile-inventory-bottom-nav\s*\{[\s\S]*position:\s*fixed;[\s\S]*grid-template-columns:\s*repeat\(var\(--rz-mobile-nav-count, 5\), minmax\(0, 1fr\)\);[\s\S]*background:\s*rgba\(255, 255, 255, 0\.98\);/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-nav-item\.is-active\s*\{[\s\S]*color:\s*var\(--rz-mobile-proposal-green\);/,
)

// Mobile Voorraad owns the fixed bottom action bar; passive feedback must sit above it.
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\) \.rz-app-feedback-bar-base,[\s\S]*display:\s*none\s*!important;/,
)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\)[\s\S]*inset:\s*auto 0 calc\(60px \+ env\(safe-area-inset-bottom\)\) 0\s*!important;/,
)

console.log('MOBILE_UI_CONFORMITY_GREEN')
