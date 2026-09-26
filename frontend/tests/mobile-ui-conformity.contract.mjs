import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const mobileAlmostOutSource = readFileSync(new URL('../src/features/almostOut/MobileAlmostOut.jsx', import.meta.url), 'utf8')
const mobileShoppingSource = readFileSync(new URL('../src/features/shopping/MobileShopping.jsx', import.meta.url), 'utf8')
const mobileShoppingCss = readFileSync(new URL('../src/features/shopping/mobileShopping.css', import.meta.url), 'utf8')
const mobileKassaSource = readFileSync(new URL('../src/features/kassa/MobileKassa.jsx', import.meta.url), 'utf8')
const mobileKassaCss = readFileSync(new URL('../src/features/kassa/mobileKassa.css', import.meta.url), 'utf8')
const mobileInventorySource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const mobileInventoryCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const mobileArticleSource = readFileSync(new URL('../src/features/articles/MobileArticlePage.jsx', import.meta.url), 'utf8')
const mobileArticleCss = readFileSync(new URL('../src/features/articles/mobileArticleDetail.css', import.meta.url), 'utf8')
const mobileComponentsCss = readFileSync(new URL('../src/ui/mobileComponents.css', import.meta.url), 'utf8')
const mobileModuleHeaderSource = readFileSync(new URL('../src/ui/MobileModuleHeader.jsx', import.meta.url), 'utf8')
const mobileAppChromeSource = readFileSync(new URL('../src/app/MobileAppChrome.jsx', import.meta.url), 'utf8')
const inventoryResponsiveSource = readFileSync(new URL('../src/pages/VoorraadResponsive.jsx', import.meta.url), 'utf8')
const almostOutResponsiveSource = readFileSync(new URL('../src/features/almostOut/AlmostOutResponsive.jsx', import.meta.url), 'utf8')
const shoppingResponsiveSource = readFileSync(new URL('../src/features/shopping/ShoppingResponsive.jsx', import.meta.url), 'utf8')
const articleResponsiveSource = readFileSync(new URL('../src/features/articles/ArticlePageResponsive.jsx', import.meta.url), 'utf8')
const mobileViewportSource = readFileSync(new URL('../src/app/mobileViewport.js', import.meta.url), 'utf8')
const mobileHomeSource = readFileSync(new URL('../src/features/home/MobileHomePage.jsx', import.meta.url), 'utf8')
const mobileHomeCss = readFileSync(new URL('../src/features/home/mobileHome.css', import.meta.url), 'utf8')
const mobileSupportSource = readFileSync(new URL('../src/features/support/MobileSupportInbox.jsx', import.meta.url), 'utf8')
const mobileSupportCss = readFileSync(new URL('../src/features/support/mobileSupportInbox.css', import.meta.url), 'utf8')
const mobileAppChromeCss = readFileSync(new URL('../src/app/mobileAppChrome.css', import.meta.url), 'utf8')
const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const themeCss = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')

// Sole visual conformance authority for mobile roots already migrated to the
// new PO-approved design. Functional mobile contracts remain separate.
const MOBILE_UI_MANIFEST = Object.freeze([
  { key: 'startpagina', source: mobileHomeSource, css: mobileHomeCss, header: /<MobileModuleHeader title="Startpagina"/ },
  { key: 'voorraad', source: mobileInventorySource, css: mobileInventoryCss, header: /<MobileModuleHeader title="Voorraad"/ },
  { key: 'voorraad-detail', source: mobileArticleSource, css: mobileArticleCss, header: /<MobileModuleHeader title="Artikel in Voorraad"/ },
  { key: 'bijna-op', source: mobileAlmostOutSource, css: mobileInventoryCss, header: /<MobileModuleHeader title="Bijna op"/ },
  { key: 'boodschappen', source: mobileShoppingSource, css: mobileShoppingCss, header: /<MobileModuleHeader title="Boodschappen"/ },
  { key: 'kassa', source: mobileKassaSource, css: mobileKassaCss, header: /<MobileModuleHeader[^>]*mobile-kassa-header/ },
  { key: 'meldingen', source: mobileSupportSource, css: mobileSupportCss, header: /<MobileModuleHeader title="Meldingen"/ },
])
assert.deepEqual(MOBILE_UI_MANIFEST.map(({ key }) => key), ['startpagina', 'voorraad', 'voorraad-detail', 'bijna-op', 'boodschappen', 'kassa', 'meldingen'])
for (const screen of MOBILE_UI_MANIFEST) {
  assert.match(screen.source, screen.header, screen.key + ' moet de gedeelde MobileModuleHeader gebruiken')
  for (const declaration of screen.css.matchAll(/font-size\s*:\s*([^;}]+)/gi)) {
    assert.match(declaration[1].trim(), /var\(--font-size-ui-(?:body|title)\)/, screen.key + ' gebruikt een niet-toegestane lettergrootte: ' + declaration[1].trim())
  }
  assert.doesNotMatch(screen.css, /#006b3c|#005630/i, screen.key + ' gebruikt een alternatieve primaire groentint')
}

assert.match(mobileHomeSource, /data-testid="mobile-home-page"/)
assert.match(mobileHomeSource, /<MobileModuleHeader title="Startpagina" testId="mobile-home-header" \/>/)
assert.match(mobileHomeSource, /mobile-home-customize/)
assert.match(mobileHomeSource, /inhuis-mobile-home-order:/)
assert.match(mobileHomeSource, /listHouseholdThreads\('Open'\)/)
assert.match(mobileHomeSource, /rz-inhuis-wordmark-in/)
assert.match(mobileHomeCss, /color:\s*rgb\(40 169 158\)/i)
assert.match(mobileHomeCss, /Segoe Script/)
assert.match(mobileHomeCss, /url\('\/inhuis-green-wallpaper\.svg'\)/)

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
assert.match(mobileModuleHeaderSource, /rz-mobile-module-header-wordmark/)
assert.match(mobileComponentsCss, /\.rz-mobile-module-header-wordmark-huis\s*\{[\s\S]*color:\s*#fff;/i)
assert.match(mobileComponentsCss, /\.rz-mobile-module-header-wordmark-in\s*\{[\s\S]*color:\s*rgb\(40 169 158\);/i)
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
assert.match(mobileViewportSource, /MOBILE_APP_MEDIA_QUERY = '\(max-width: 720px\)'/)
assert.match(mobileAppChromeSource, /useMobileAppViewport\(\)/)
for (const responsiveSource of [inventoryResponsiveSource, almostOutResponsiveSource, shoppingResponsiveSource, articleResponsiveSource]) {
  assert.match(responsiveSource, /useMobileAppViewport\(\)/)
  assert.doesNotMatch(responsiveSource, /isMobileInventoryEligibleContext|isPlatformSuperuser|isHouseholdAdmin|display_role|context_type\s*===\s*['"]system['"]/)
}
assert.match(mobileAppChromeSource, /MobileRecentActionsBar/)
assert.match(mobileAppChromeSource, /<MobileBackControl testId="mobile-global-back" \/>/)
assert.doesNotMatch(mobileAppChromeSource, /location\.pathname !== '\/home'/)
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
assert.match(
  mobileAppChromeCss,
  /\.rz-mobile-app-chrome > \.rz-mobile-back-control\s*\{[\s\S]*position:\s*fixed;[\s\S]*left:\s*10px;/,
)
assert.match(
  mobileAppChromeCss,
  /\.rz-mobile-app-chrome:not\(:has\(\.rz-header, \.rz-mobile-module-header\)\)\s*\{[\s\S]*padding-top:\s*calc\(58px \+ env\(safe-area-inset-top\)\);/,
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
