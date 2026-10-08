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
const mobileRecentActionsSource = readFileSync(new URL('../src/ui/MobileRecentActionsBar.jsx', import.meta.url), 'utf8')
const dataTableSource = readFileSync(new URL('../src/ui/DataTable.jsx', import.meta.url), 'utf8')
const inventoryResponsiveSource = readFileSync(new URL('../src/pages/VoorraadResponsive.jsx', import.meta.url), 'utf8')
const almostOutResponsiveSource = readFileSync(new URL('../src/features/almostOut/AlmostOutResponsive.jsx', import.meta.url), 'utf8')
const shoppingResponsiveSource = readFileSync(new URL('../src/features/shopping/ShoppingResponsive.jsx', import.meta.url), 'utf8')
const articleResponsiveSource = readFileSync(new URL('../src/features/articles/ArticlePageResponsive.jsx', import.meta.url), 'utf8')
const mobileViewportSource = readFileSync(new URL('../src/app/mobileViewport.js', import.meta.url), 'utf8')
const mobileHomeSource = readFileSync(new URL('../src/features/home/MobileHomePage.jsx', import.meta.url), 'utf8')
const desktopHomeSource = readFileSync(new URL('../src/features/home/HomePage.jsx', import.meta.url), 'utf8')
const mobileHomeCss = readFileSync(new URL('../src/features/home/mobileHome.css', import.meta.url), 'utf8')
const mobileSupportSource = readFileSync(new URL('../src/features/support/MobileSupportInbox.jsx', import.meta.url), 'utf8')
const mobileSupportCss = readFileSync(new URL('../src/features/support/mobileSupportInbox.css', import.meta.url), 'utf8')
const mobileUnpackSource = readFileSync(new URL('../src/features/receipts/ReceiptsPage.jsx', import.meta.url), 'utf8')
const mobileUnpackDetailSource = readFileSync(new URL('../src/features/stores/StoreBatchDetailPage.jsx', import.meta.url), 'utf8')
const mobileUnpackCss = readFileSync(new URL('../src/features/receipts/mobileReceipts.css', import.meta.url), 'utf8')
const mobileAppChromeCss = readFileSync(new URL('../src/app/mobileAppChrome.css', import.meta.url), 'utf8')
const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const themeCss = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')
const buttonSource = readFileSync(new URL('../src/ui/Button.jsx', import.meta.url), 'utf8')

// Sole visual conformance authority for mobile roots already migrated to the
// new PO-approved design. Functional mobile contracts remain separate.
const MOBILE_UI_MANIFEST = Object.freeze([
  { key: 'startpagina', source: mobileHomeSource, css: mobileHomeCss, header: /<MobileModuleHeader title="Dashboard"/ },
  { key: 'voorraad', source: mobileInventorySource, css: mobileInventoryCss, header: /<MobileModuleHeader title="Voorraad"/ },
  { key: 'voorraad-detail', source: mobileArticleSource, css: mobileArticleCss, header: /<MobileModuleHeader title="Artikel in Voorraad"/ },
  { key: 'bijna-op', source: mobileAlmostOutSource, css: mobileInventoryCss, header: /<MobileModuleHeader title="Bijna op"/ },
  { key: 'boodschappen', source: mobileShoppingSource, css: mobileShoppingCss, header: /<MobileModuleHeader title="Boodschappen"/ },
  { key: 'kassa', source: mobileKassaSource, css: mobileKassaCss, header: /<MobileModuleHeader[^>]*mobile-kassa-header/ },
  { key: 'meldingen', source: mobileSupportSource, css: mobileSupportCss, header: /<MobileModuleHeader title="Meldingen"/ },
  { key: 'uitpakken', source: mobileUnpackSource, css: mobileUnpackCss, header: /<MobileModuleHeader title="Uitpakken" testId="mobile-unpack-header"/ },
  { key: 'uitpakken-detail', source: mobileUnpackDetailSource, css: mobileUnpackCss, header: /<MobileModuleHeader title="Kassabon" testId="mobile-unpack-detail-header"/ },
])
assert.deepEqual(MOBILE_UI_MANIFEST.map(({ key }) => key), ['startpagina', 'voorraad', 'voorraad-detail', 'bijna-op', 'boodschappen', 'kassa', 'meldingen', 'uitpakken', 'uitpakken-detail'])
for (const screen of MOBILE_UI_MANIFEST) {
  assert.match(screen.source, screen.header, screen.key + ' moet de gedeelde MobileModuleHeader gebruiken')
  for (const declaration of screen.css.matchAll(/font-size\s*:\s*([^;}]+)/gi)) {
    assert.match(declaration[1].trim(), /var\(--font-size-ui-(?:body|title)\)/, screen.key + ' gebruikt een niet-toegestane lettergrootte: ' + declaration[1].trim())
  }
  assert.doesNotMatch(screen.css, /#006b3c|#005630/i, screen.key + ' gebruikt een alternatieve primaire groentint')
  if (screen.key.startsWith('uitpakken')) {
    assert.match(screen.css, /\.rz-mobile-unpack-detail-content select,[\s\S]*font-size:\s*var\(--font-size-ui-body\)\s*!important;/, screen.key + ' moet dropdowns op de mobiele body-lettergrootte houden')
  }
}

assert.match(mobileHomeSource, /data-testid="mobile-home-page"/)
assert.match(mobileHomeSource, /<MobileModuleHeader title="Dashboard" testId="mobile-home-header" \/>/)
assert.match(mobileHomeSource, /data-testid="dashboard-status-notifications"/)
assert.match(mobileHomeSource, /data-testid="dashboard-status-shopping"/)
assert.match(mobileHomeSource, /data-testid="dashboard-status-open-receipts"/)
assert.match(mobileHomeSource, /data-testid="dashboard-status-downloadable-receipts"/)
assert.match(mobileHomeSource, /data-testid="dashboard-status-almost-out"/)
assert.match(mobileHomeSource, /PERIODS\.map/)
assert.match(mobileHomeSource, /data-testid=\{'dashboard-period-' \+ item\.key\}/)
assert.match(mobileHomeSource, /rz-dashboard-grid/)
assert.match(mobileHomeSource, /rz-dashboard-shared-legend/)
assert.match(mobileHomeSource, /aria-label="Productfamilies"/)
assert.match(mobileHomeSource, /openBarDrilldown/)
assert.doesNotMatch(mobileHomeSource, /function InHuisWordmark\(/)
assert.match(mobileHomeSource, /function EmptyDashboardChart\(\)/)
assert.match(mobileHomeSource, /const visibleCards = dashboard \? orderedCards : loadingCards/)
assert.match(mobileHomeSource, /aria-disabled=\{!dashboard\}/)
assert.match(desktopHomeSource, /if \(!actionAvailability\.ready && !isMobileViewport\)/)
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
assert.match(mobileModuleHeaderSource, /import BrandLogo from '\.\/BrandLogo\.jsx'/)
assert.match(mobileModuleHeaderSource, /<BrandLogo variant="header" \/>/)
assert.match(mobileAppChromeSource, /<MobileModuleHeader[\s\S]*className="rz-mobile-app-header"[\s\S]*showBack/)
assert.match(mobileAppChromeSource, /mobileRouteTitle\(location\.pathname\)/)
assert.match(mobileAppChromeCss, /\.rz-mobile-app-chrome > \.rz-mobile-app-header\s*\{[\s\S]*position:\s*sticky;[\s\S]*top:\s*0;/)
assert.match(mobileAppChromeCss, /\.rz-mobile-app-chrome \.rz-mobile-module-header:not\(\.rz-mobile-app-header\)/)
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
assert.match(mobileViewportSource, /screenWidth/)
assert.match(mobileViewportSource, /physicalWidth <= 720/)
assert.match(mobileViewportSource, /window\.screen\?\.width/)
assert.match(mobileAppChromeSource, /useMobileAppViewport\(\)/)
for (const responsiveSource of [inventoryResponsiveSource, almostOutResponsiveSource, shoppingResponsiveSource, articleResponsiveSource]) {
  assert.match(responsiveSource, /useMobileAppViewport\(\)/)
  assert.doesNotMatch(responsiveSource, /isMobileInventoryEligibleContext|isPlatformSuperuser|isHouseholdAdmin|display_role|context_type\s*===\s*['"]system['"]/)
}
assert.match(mobileAppChromeSource, /MobileRecentActionsBar/)
assert.match(mobileAppChromeSource, /backTestId="mobile-global-back"/)
assert.match(mobileModuleHeaderSource, /<MobileBackControl testId=\{backTestId\} onBack=\{onBack\} \/>/)
assert.match(mobileAppChromeSource, /function handleKassaBack\(\)/)
assert.match(mobileAppChromeSource, /new Event\('inhuis:mobile-kassa-back', \{ cancelable: true \}\)/)
assert.match(mobileAppChromeSource, /title: 'Inhuis verlaten'/)
assert.match(mobileAppChromeSource, /primaryActionLabel: 'Uitloggen'/)
assert.match(mobileAppChromeSource, /secondaryActionLabel: 'Annuleren'/)
assert.doesNotMatch(mobileAppChromeSource, /location\.pathname !== '\/home'/)
assert.match(mobileAppChromeSource, /testId="mobile-global-bottom-nav"/)
assert.match(mobileAppChromeSource, /activeActionKey\(pathname\)/)
assert.match(mobileAppChromeSource, /MANDATORY_BOTTOM_NAV_KEY = 'bijna-op'/)
assert.match(mobileAppChromeSource, /const excludedKeys = \[MANDATORY_BOTTOM_NAV_KEY\]/)
assert.match(mobileAppChromeSource, /if \(activeKey && activeKey !== MANDATORY_BOTTOM_NAV_KEY\) excludedKeys\.push\(activeKey\)/)
assert.match(mobileAppChromeSource, /limit: mandatoryTile \? 3 : 4/)
assert.match(mobileAppChromeSource, /const iconType = MOBILE_ICON_TYPE_BY_KEY\[tile\.key\] \|\| null/)
assert.match(mobileAppChromeSource, /icon: iconType \? null : tile\.icon/)
assert.match(mobileAppChromeSource, /showLabel: false/)
assert.match(mobileAppChromeSource, /MORE_NAV_ITEM[\s\S]*showLabel: true/)
assert.match(mobileRecentActionsSource, /aria-label=\{item\.label\}/)
assert.match(mobileRecentActionsSource, /item\.showLabel \? <span>\{item\.label\}<\/span> : null/)
assert.match(dataTableSource, /useMobileAppViewport/)
assert.match(dataTableSource, /const effectivePagination = Boolean\(pagination \|\| isMobileViewport\)/)
assert.match(dataTableSource, /<Pagination page=\{page\} pageCount=\{pageCount\}/)
assert.match(routerSource, /MobileAppChrome/)
assert.doesNotMatch(themeCss, /body:has\(\[data-testid="mobile-inventory-page"\]\)/)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-app-chrome"\]\) \.rz-app-feedback-bar-base,[\s\S]*display:\s*none\s*!important;/,
)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-app-chrome"\]\)[\s\S]*padding-bottom:\s*calc\(90px \+ env\(safe-area-inset-bottom\)\)\s*!important;/,
)

// One shared mobile back control is used by both module and generic headers.
assert.match(mobileModuleHeaderSource, /className="rz-mobile-back-control"/)
assert.match(mobileModuleHeaderSource, />\s*Terug\s*</)
assert.match(mobileModuleHeaderSource, /navigate\(-1\)/)
assert.match(
  mobileComponentsCss,
  /\.rz-mobile-back-control\s*\{[\s\S]*min-height:\s*44px;[\s\S]*background:\s*var\(--color-mobile-ui-primary\);/,
)
assert.match(mobileAppChromeCss, /\.rz-mobile-app-header \.rz-brandlogo-header/)
assert.match(mobileAppChromeCss, /\.rz-mobile-app-bottom-space\s*\{[\s\S]*display:\s*block;/)
assert.doesNotMatch(mobileAppChromeCss, /position:\s*fixed;[\s\S]*\.rz-mobile-back-control/)


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

assert.match(mobileAppChromeSource, /inhuis:mobile-home-back/)
assert.match(mobileComponentsCss, /min-width:\s*56px/)
assert.match(mobileAppChromeCss, /left:\s*8px/)

// Meldingen blijft als dashboardstatus doorklikbaar en als actie beschikbaar in de globale onderbalk.
assert.match(mobileHomeSource, /openStatus\('meldingen'\)/)
assert.match(mobileHomeSource, /key: 'meldingen', clickable: true/)
assert.doesNotMatch(mobileAppChromeSource, /function mobileNavIconType/)


// Exporteren is app-breed desktop-only op de centrale mobiele viewport.
assert.match(buttonSource, /children\.trim\(\)\.toLowerCase\(\) === 'exporteren'/)
assert.match(buttonSource, /data-mobile-export-action=\{isExportAction \? 'true' : undefined\}/)
assert.match(themeCss, /button\[data-mobile-export-action="true"\]/)
assert.match(themeCss, /@media \(max-width: 720px\)/)
