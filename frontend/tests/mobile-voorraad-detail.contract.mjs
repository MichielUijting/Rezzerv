import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  buildHouseholdSettingsPayload,
  buildMobileArticleInventoryRows,
  buildShoppingListPayload,
  chooseMobileInventoryRow,
  filterPurchaseHistory,
  formatMobileLocation,
  isMobileArticleAlmostOut,
} from '../src/features/articles/mobileArticleDetailModel.js'

const liveRows = [
  {
    id: 'inventory-a',
    household_article_id: 'article-1',
    artikel: 'Broccoli',
    aantal: 2,
    space_id: 'space-kitchen',
    sublocation_id: 'sublocation-cupboard',
    locatie: 'Keuken',
    sublocatie: 'Keukenkast',
  },
  {
    id: 'inventory-b',
    household_article_id: 'article-1',
    artikel: 'Broccoli',
    aantal: 1,
    space_id: 'space-cellar',
    sublocation_id: 'sublocation-shelf',
    locatie: 'Kelder',
    sublocatie: 'Plank',
  },
  {
    id: 'inventory-same-name-other-id',
    household_article_id: 'article-2',
    artikel: 'Broccoli',
    aantal: 9,
  },
  {
    id: 'inventory-other',
    household_article_id: 'article-3',
    artikel: 'Kaas',
    aantal: 3,
  },
]

const rows = buildMobileArticleInventoryRows(liveRows, 'article-1', 'Broccoli')
assert.equal(rows.length, 2, 'stable household article id must exclude same-name rows with another id')
assert.equal(rows[0].quantity, 2)
assert.equal(formatMobileLocation(rows[0]), 'Keuken / Keukenkast')
assert.equal(chooseMobileInventoryRow(rows, { default_sublocation_id: 'sublocation-shelf' })?.id, 'inventory-b')
assert.equal(chooseMobileInventoryRow(rows, { default_location_id: 'space-kitchen' })?.id, 'inventory-a')
assert.equal(isMobileArticleAlmostOut(2, 2), true)
assert.equal(isMobileArticleAlmostOut(3, 2), false)
assert.equal(isMobileArticleAlmostOut(0, null), false)

const legacyRows = buildMobileArticleInventoryRows([
  { id: 'legacy-broccoli', artikel: 'Broccoli', aantal: 1 },
  { id: 'legacy-cheese', artikel: 'Kaas', aantal: 1 },
], 'article::Broccoli', 'Broccoli')
assert.deepEqual(legacyRows.map((row) => row.id), ['legacy-broccoli'])

const settingsPayload = buildHouseholdSettingsPayload({
  min_stock: 2,
  ideal_stock: 4,
  favorite_store: 'Jumbo',
  average_price: 1.79,
  status: 'active',
  default_location_id: 'space-kitchen',
  default_sublocation_id: 'sublocation-cupboard',
  auto_restock: true,
  packaging_unit: 'stuk',
  packaging_quantity: 1,
  notes: 'Bij voorkeur biologisch',
}, 'AH')
assert.equal(settingsPayload.favorite_store, 'AH')
assert.equal(settingsPayload.min_stock, 2)
assert.equal(settingsPayload.default_location_id, 'space-kitchen')
assert.equal(settingsPayload.notes, 'Bij voorkeur biologisch')

const shoppingPayload = buildShoppingListPayload({
  article_name: 'Broccoli',
  article_group_name: 'Groente',
  product_type_name: 'Vers',
}, 'article-1')
assert.deepEqual(shoppingPayload, {
  article_name: 'Broccoli',
  article_group_name: 'Groente',
  product_type_name: 'Vers',
  source_type: 'household_article',
  source_id: 'article-1',
})

const purchaseHistory = filterPurchaseHistory([
  { id: '1', event_type: 'purchase' },
  { id: '2', event_type: 'manual_adjustment' },
  { id: '3', type: 'Aankoop' },
])
assert.deepEqual(purchaseHistory.map((item) => item.id), ['1', '3'])

const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const responsiveSource = readFileSync(new URL('../src/features/articles/ArticlePageResponsive.jsx', import.meta.url), 'utf8')
const mobileSource = readFileSync(new URL('../src/features/articles/MobileArticlePage.jsx', import.meta.url), 'utf8')

assert.match(routerSource, /import ArticlePageResponsive from '\.\.\/\.\.\/features\/articles\/ArticlePageResponsive\.jsx'/)
assert.match(routerSource, /path: '\/voorraad\/:articleId'.*<ArticlePageResponsive \/>/)
assert.match(responsiveSource, /MOBILE_INVENTORY_MEDIA_QUERY/)
assert.match(responsiveSource, /isMobileInventoryEligibleContext\(context\)/)
assert.match(responsiveSource, /<MobileArticlePage \/>/)
assert.match(responsiveSource, /<ArticlePage \/>/)

assert.match(mobileSource, /data-testid="mobile-article-detail-page"/)
assert.match(mobileSource, /<QuantityStepper/)
assert.match(mobileSource, /decreaseTestId="mobile-article-stock-minus"/)
assert.match(mobileSource, /increaseTestId="mobile-article-stock-plus"/)
assert.match(mobileSource, /data-testid="mobile-article-favorite-store-action"/)
assert.match(mobileSource, /data-testid="mobile-article-purchase-history-action"/)
assert.match(mobileSource, /data-testid="mobile-article-add-to-shopping-list"/)
assert.match(mobileSource, />Voorkeurswinkel</)
assert.match(mobileSource, />Aankoophistorie</)
assert.match(mobileSource, />Naar inkooplijstje</)
assert.match(mobileSource, /\/api\/shopping-list\/items/)
assert.match(mobileSource, /toegevoegd aan Winkelen/)
assert.match(mobileSource, /locationTrackingEnabled \? \(/)
assert.match(mobileSource, /data-testid="mobile-article-location-row"/)
assert.match(mobileSource, /event_type: direction > 0 \? 'adjustment' : 'consume'/)
assert.doesNotMatch(mobileSource, /Naar boodschappen/i)
assert.doesNotMatch(mobileSource, /Verbruik registreren/i)
assert.doesNotMatch(mobileSource, />Voorraad aanpassen</)
assert.doesNotMatch(mobileSource, />Afboeken</)
assert.doesNotMatch(mobileSource, />\s*Opslaan(?:…)?\s*</)
assert.match(mobileSource, /useAppFeedback\(\)/)
assert.match(mobileSource, /showFeedback\(\{ variant: 'success'/)
assert.doesNotMatch(mobileSource, /setFeedback|rz-mobile-article-feedback|function MinusIcon|function PlusIcon/)

console.log('MOBILE_VOORRAAD_DETAIL_CONTRACT_GREEN')
