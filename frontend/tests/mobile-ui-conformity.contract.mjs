import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const mobileInventorySource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const mobileInventoryCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const mobileArticleSource = readFileSync(new URL('../src/features/articles/MobileArticlePage.jsx', import.meta.url), 'utf8')
const mobileArticleCss = readFileSync(new URL('../src/features/articles/mobileArticleDetail.css', import.meta.url), 'utf8')
const mobileComponentsCss = readFileSync(new URL('../src/ui/mobileComponents.css', import.meta.url), 'utf8')
const mobileModuleHeaderSource = readFileSync(new URL('../src/ui/MobileModuleHeader.jsx', import.meta.url), 'utf8')
const mobileAppChromeSource = readFileSync(new URL('../src/app/MobileAppChrome.jsx', import.meta.url), 'utf8')
const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const themeCss = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')

// Sole visual conformance authority for mobile roots already migrated to the
// new PO-approved design. Functional mobile contracts remain separate.
const MIGRATED_MOBILE_UI = Object.freeze(['voorraad', 'voorraad-detail'])
assert.deepEqual(MIGRATED_MOBILE_UI, ['voorraad', 'voorraad-detail'])

assert.match(mobileInventorySource, /data-testid="mobile-inventory-page"/)
assert.match(mobileInventorySource, /<MobileModuleHeader title="Voorraad" testId="mobile-inventory-header" \/>/)
assert.match(mobileInventorySource, /<QuantityStepper/)
assert.doesNotMatch(mobileInventorySource, /MobileRecentActionsBar|selectRecentActionTiles|MORE_NAV_ITEM/)
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
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-chevron\s*\{[\s\S]*cursor:\s*pointer;/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-card:hover \.rz-mobile-inventory-chevron\s*\{[\s\S]*color:\s*var\(--color-mobile-ui-primary\);/,
)

// Shared mobile chrome owns navigation for every protected mobile route.
assert.match(mobileAppChromeSource, /MobileRecentActionsBar/)
assert.match(mobileAppChromeSource, /testId="mobile-global-bottom-nav"/)
assert.match(mobileAppChromeSource, /activeActionKey\(pathname\)/)
assert.match(mobileAppChromeSource, /excludeKeys:\s*activeKey \? \[activeKey\] : \[\]/)
assert.match(routerSource, /MobileAppChrome/)
assert.doesNotMatch(themeCss, /body:has\(\[data-testid="mobile-inventory-page"\]\)/)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-app-chrome"\]\) \.rz-app-feedback-bar-base,[\s\S]*display:\s*none\s*!important;/,
)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-app-chrome"\]\)[\s\S]*padding-bottom:\s*calc\(70px \+ env\(safe-area-inset-bottom\)\)\s*!important;/,
)

// One shared mobile back control is used by both module and generic headers.
assert.match(mobileModuleHeaderSource, /className="rz-mobile-back-control"/)
assert.match(mobileModuleHeaderSource, />\s*Terug\s*</)
assert.match(mobileModuleHeaderSource, /navigate\(-1\)/)
assert.match(
  mobileComponentsCss,
  /\.rz-mobile-back-control\s*\{[\s\S]*min-height:\s*44px;[\s\S]*background:\s*var\(--color-mobile-ui-primary\);/,
)

assert.match(mobileArticleSource, /<MobileModuleHeader title="Artikel in Voorraad" testId="mobile-article-header" \/>/)
assert.doesNotMatch(mobileArticleSource, /mobile-article-back-to-inventory|navigate\('\/voorraad'\)/)
assert.match(mobileArticleSource, /CatalogArticleThumbnail/)
assert.match(mobileArticleSource, /valueEditable=\{canDirectEditQuantity\}/)
assert.match(
  mobileArticleCss,
  /\.rz-mobile-article-screen\s*\{[\s\S]*url\('\/inhuis-green-wallpaper\.svg'\)[\s\S]*background-color:\s*#EEF7F0/i,
)
assert.doesNotMatch(mobileArticleCss, /inhuis-orange-wallpaper|backdrop-filter/i)
assert.match(
  mobileArticleCss,
  /\.rz-mobile-article-card\s*\{[\s\S]*border-radius:\s*12px;[\s\S]*background:\s*#ffffff;[\s\S]*box-shadow:\s*none;/i,
)
assert.match(
  mobileArticleCss,
  /\.rz-mobile-article-action-row--primary\s*\{[\s\S]*background:\s*var\(--color-mobile-ui-primary\);[\s\S]*color:\s*#ffffff;/i,
)

assert.doesNotMatch(mobileInventoryCss, /rz-mobile-inventory-quick-feedback|rz-mobile-inventory-topbar|rz-mobile-inventory-bottom-nav/)

console.log('MOBILE_UI_CONFORMITY_GREEN')
