import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  buildMobileAlmostOutRows,
  formatAlmostOutQuantity,
} from '../src/features/almostOut/mobileAlmostOutModel.js'

const rows = buildMobileAlmostOutRows([
  {
    household_article_id: 'article-1',
    household_article_name: 'Halfvolle melk',
    product_name: 'Melk halfvol',
    image_url: 'https://images.example.test/melk.jpg',
    current_quantity: 1,
    min_stock: 2,
    ideal_stock: 4,
    amount_to_buy: 3,
    packaging_quantity: 1,
    packaging_unit: 'liter',
    primary_location: {
      space_name: 'Keuken',
      sublocation_name: 'Koelkast',
    },
  },
])

assert.equal(rows.length, 1)
assert.equal(rows[0].detailId, 'article-1')
assert.equal(rows[0].householdName, 'Halfvolle melk')
assert.equal(rows[0].productName, 'Melk halfvol')
assert.equal(rows[0].imageUrl, 'https://images.example.test/melk.jpg')
assert.equal(rows[0].currentQuantity, 1)
assert.equal(rows[0].minStock, 2)
assert.equal(rows[0].idealStock, 4)
assert.equal(rows[0].amountToBuy, 3)
assert.equal(rows[0].packaging, '1 liter')
assert.equal(rows[0].location, 'Keuken / Koelkast')
assert.equal(formatAlmostOutQuantity(2.5), '2.5')

const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const responsiveSource = readFileSync(new URL('../src/features/almostOut/AlmostOutResponsive.jsx', import.meta.url), 'utf8')
const mobileSource = readFileSync(new URL('../src/features/almostOut/MobileAlmostOut.jsx', import.meta.url), 'utf8')
const inventoryCss = readFileSync(new URL('../src/pages/mobileVoorraad.css', import.meta.url), 'utf8')
const typographyCss = readFileSync(new URL('../src/ui/typography.css', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')

assert.match(routerSource, /import AlmostOutResponsive from '\.\.\/\.\.\/features\/almostOut\/AlmostOutResponsive\.jsx'/)
assert.match(routerSource, /path: '\/bijna-op'.*<AlmostOutResponsive \/>/)

assert.match(responsiveSource, /MOBILE_INVENTORY_MEDIA_QUERY/)
assert.match(responsiveSource, /isMobileInventoryEligibleContext\(context\)/)
assert.match(responsiveSource, /fetchHouseholdOnboarding\(context, \{ force: true \}\)/)
assert.match(responsiveSource, /product_configuration\?\.location_tracking_level/)
assert.match(responsiveSource, /<MobileAlmostOut locationTrackingEnabled=\{locationTrackingEnabled\} \/>/)
assert.match(responsiveSource, /<AlmostOutPage \/>/)

assert.match(mobileSource, /data-testid="mobile-almost-out-page"/)
assert.match(mobileSource, /\.\.\/\.\.\/pages\/mobileVoorraad\.css/)
assert.match(mobileSource, /\/api\/households\/\$\{encodeURIComponent\(householdId\)\}\/almost-out/)
assert.match(mobileSource, /Zoek artikel, product of locatie/)
assert.match(mobileSource, /Te kopen hoog–laag/)
assert.match(mobileSource, /Huidig laag–hoog/)
assert.match(mobileSource, /data-testid="mobile-almost-out-location-filter"/)
assert.match(mobileSource, /Te kopen \{formatAlmostOutQuantity\(row\.amountToBuy\)\}/)
assert.match(mobileSource, /CatalogArticleThumbnail/)
assert.match(mobileSource, /imageUrl=\{row\.imageUrl\}/)
assert.match(mobileSource, /\/voorraad\/\$\{encodeURIComponent\(row\.detailId\)\}/)
assert.doesNotMatch(mobileSource, /Alles naar Winkelen/i)
assert.doesNotMatch(mobileSource, /Naar Winkelen/i)

assert.match(inventoryCss, /rz-mobile-inventory-toolbar/)
assert.match(inventoryCss, /rz-mobile-inventory-card/)
assert.match(inventoryCss, /rz-mobile-inventory-quantity/)
assert.match(typographyCss, /button,[\s\S]*input,[\s\S]*select,[\s\S]*textarea,[\s\S]*option[\s\S]*font-size: var\(--font-size-ui-body\) !important;/)
assert.match(appSource, /data-testid="app-feedback-bar-scroll-clearance"/)

console.log('MOBILE_ALMOST_OUT_CONTRACT_GREEN')
