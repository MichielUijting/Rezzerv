import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  MOBILE_APP_MEDIA_QUERY,
  isMobileAppViewport,
} from '../src/app/mobileViewport.js'
import {
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from '../src/features/home/recentActionUsage.js'
import {
  applyInventoryRowQuantity,
  buildExactInventoryMutation,
  buildQuickInventoryMutation,
  selectExactInventoryTarget,
  selectQuickInventoryTarget,
} from '../src/pages/mobileInventoryQuickActions.js'

assert.equal(MOBILE_APP_MEDIA_QUERY, '(max-width: 720px)')
assert.equal(isMobileAppViewport({ matches: true }), true)
assert.equal(isMobileAppViewport({ matches: false }), false)
assert.equal(isMobileAppViewport(null), false)

const routerSource = readFileSync(new URL('../src/app/router/AppRouter.jsx', import.meta.url), 'utf8')
const selectorSource = readFileSync(new URL('../src/pages/VoorraadResponsive.jsx', import.meta.url), 'utf8')
const selectorCss = readFileSync(new URL('../src/pages/voorraadResponsive.css', import.meta.url), 'utf8')
const mobileSource = readFileSync(new URL('../src/pages/MobileVoorraad.jsx', import.meta.url), 'utf8')
const mobileAppChromeSource = readFileSync(new URL('../src/app/MobileAppChrome.jsx', import.meta.url), 'utf8')
const homeSource = readFileSync(new URL('../src/features/home/HomePage.jsx', import.meta.url), 'utf8')

assert.match(routerSource, /import VoorraadResponsive from '\.\.\/\.\.\/pages\/VoorraadResponsive\.jsx'/)
assert.match(routerSource, /path: '\/voorraad'.*<VoorraadResponsive \/>/)
assert.match(selectorSource, /const isMobileViewport = useMobileAppViewport\(\)/)
assert.match(selectorSource, /if \(isMobileViewport\)/)
assert.doesNotMatch(selectorSource, /isMobileInventoryEligibleContext|isPlatformSuperuser|isHouseholdAdmin/)
assert.match(selectorSource, /product_configuration\?\.location_tracking_level/)
assert.match(selectorSource, /fetchHouseholdOnboarding\(context, \{ force: true \}\)/)
assert.doesNotMatch(selectorSource, /primary_use_case\s*===\s*['"]waar_inhuis['"]/) 
assert.match(selectorSource, /<MobileVoorraad locationTrackingEnabled=\{locationTrackingEnabled\} \/>/)
assert.match(selectorSource, /data-location-tracking=\{locationTrackingEnabled \? 'enabled' : 'disabled'\}/)
assert.match(selectorSource, /<Voorraad \/>/)
assert.match(selectorCss, /rz-inventory-presentation--locationless[\s\S]*nth-child\(5\)/)
assert.match(selectorCss, /rz-inventory-presentation--locationless[\s\S]*nth-child\(6\)/)

assert.match(mobileSource, /data-testid="mobile-inventory-page"/)
assert.match(mobileSource, /<MobileModuleHeader title="Voorraad" testId="mobile-inventory-header" \/>/)
assert.match(mobileSource, /data-testid="mobile-inventory-add-incidental-purchase"/)
assert.match(mobileSource, /data-testid="mobile-inventory-location-filter"/)
assert.doesNotMatch(mobileSource, /MobileRecentActionsBar|mobile-inventory-bottom-nav|selectRecentActionTiles/)
assert.match(mobileAppChromeSource, /<MobileRecentActionsBar[\s\S]*testId="mobile-global-bottom-nav"/)
assert.match(mobileAppChromeSource, /selectRecentActionTiles/)
assert.match(mobileAppChromeSource, /readRecentActionKeys\(context\)/)
assert.match(mobileAppChromeSource, /recordRecentAction\(item\.key, context\)/)
assert.match(mobileAppChromeSource, /MANDATORY_BOTTOM_NAV_KEY = 'bijna-op'/)
assert.match(mobileAppChromeSource, /const excludedKeys = \[MANDATORY_BOTTOM_NAV_KEY\]/)
assert.match(mobileAppChromeSource, /if \(activeKey && activeKey !== MANDATORY_BOTTOM_NAV_KEY\) excludedKeys\.push\(activeKey\)/)
assert.match(mobileAppChromeSource, /limit: mandatoryTile \? 3 : 4/)
assert.match(mobileSource, /<QuantityStepper/)
assert.match(mobileSource, /valueEditable=\{Boolean\(exactQuantityTarget\)\}/)
assert.match(mobileSource, /onValueCommit=\{\(nextQuantity\) =>/)
assert.match(mobileSource, /setExactInventoryQuantity\(row, nextQuantity\)/)
assert.match(mobileSource, /testIdPrefix=\{\`mobile-inventory-/)
assert.match(mobileSource, /\/inventory-events/)
assert.match(mobileAppChromeSource, /MORE_NAV_ITEM = \{ key: 'meer', label: 'Meer', route: '', iconType: 'menu', showLabel: true, actionOnly: true \}/)
assert.match(mobileAppChromeSource, /data-testid="mobile-more-dialog"/)
assert.match(homeSource, /recordRecentAction\(tile\.key, context\)/)
assert.doesNotMatch(mobileSource, /<Header title="Voorraad"/)
assert.match(mobileSource, /locationTrackingEnabled \? 'Zoek artikel, groep of locatie' : 'Zoek artikel of groep'/)
assert.match(mobileSource, /\{ value: 'name-asc', label: 'Naam A–Z' \}/)
assert.match(mobileSource, /\{ value: 'name-desc', label: 'Naam Z–A' \}/)
assert.doesNotMatch(mobileSource, /Aantal hoog–laag/)
assert.match(mobileSource, /\.\.\.\(locationTrackingEnabled \? \[\{ value: 'location', label: 'Locatie A–Z' \}\] : \[\]\)/)
assert.match(mobileSource, /\/api\/dev\/inventory-preview/)
assert.match(mobileSource, /\/api\/article-groups\/household-articles/)
assert.match(mobileSource, /MobileArticleRow/)
assert.match(mobileSource, /imageUrl:\s*String\(item\?\.image_url/)
assert.match(mobileSource, /imageUrl=\{row\.imageUrl\}/)
assert.match(mobileSource, /gpcBrickName/)
assert.doesNotMatch(mobileSource, /GPC-groep:/)
assert.match(mobileSource, /Productfamilie:/)
assert.match(mobileSource, /Locatie:/)
assert.match(mobileSource, /Sublocatie:/)
assert.doesNotMatch(mobileSource, /row\.articleGroup \|\| 'Niet ingedeeld'/)



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
      { key: 'winkelen', label: 'Boodschappen', clickable: true },
      { key: 'bijna-op', label: 'Bijna op', clickable: true },
    ],
    limit: 4,
    excludeKeys: ['voorraad'],
  }).map((tile) => tile.key),
  ['winkelen', 'bijna-op'],
)

const quickRow = {
  inventoryEntries: [
    { inventoryId: 'inventory-small', quantity: 1, sourceIndex: 0 },
    { inventoryId: 'inventory-large', quantity: 3, sourceIndex: 1 },
  ],
}
assert.deepEqual(selectQuickInventoryTarget(quickRow, 'decrease'), {
  inventoryId: 'inventory-large',
  quantity: 3,
  sourceIndex: 1,
})
assert.deepEqual(buildQuickInventoryMutation(quickRow, 'decrease'), {
  inventory_id: 'inventory-large',
  quantity: 1,
  event_type: 'consume',
  note: 'Snelle afboeking via mobiele Voorraad.',
})
assert.deepEqual(buildQuickInventoryMutation(quickRow, 'increase'), {
  inventory_id: 'inventory-large',
  quantity: 4,
  event_type: 'adjustment',
  note: 'Snelle ophoging via mobiele Voorraad.',
})
assert.equal(selectQuickInventoryTarget({ inventoryEntries: [{ inventoryId: 'fraction', quantity: 0.5, sourceIndex: 0 }] }, 'decrease'), null)

const exactRow = {
  quantity: 2.5,
  inventoryEntries: [{ inventoryId: 'inventory-exact', quantity: 2.5, sourceIndex: 0 }],
}
assert.deepEqual(selectExactInventoryTarget(exactRow), {
  inventoryId: 'inventory-exact',
  quantity: 2.5,
  sourceIndex: 0,
})
assert.deepEqual(buildExactInventoryMutation(exactRow, '4,5'), {
  inventory_id: 'inventory-exact',
  quantity: 4.5,
  event_type: 'adjustment',
  note: 'Exact aantal aangepast via mobiele Voorraad.',
})
assert.equal(buildExactInventoryMutation({
  quantity: 5,
  inventoryEntries: [
    { inventoryId: 'inventory-a', quantity: 2, sourceIndex: 0 },
    { inventoryId: 'inventory-b', quantity: 3, sourceIndex: 1 },
  ],
}, 4), null)
assert.equal(buildExactInventoryMutation(exactRow, -1), null)

assert.match(mobileSource, /useAppFeedback\(\)/)
assert.match(mobileSource, /showFeedback\(\{[\s\S]*testId: 'mobile-inventory-quick-feedback'/)
assert.doesNotMatch(mobileSource, /mutationFeedback|setMutationFeedback/)

// Immediate UI updates retain unrelated rows and locations without network fetches.
const initialRows = [
  { id: 'household:a', quantity: 5, inventoryEntries: [
    { inventoryId: 'a-1', quantity: 3 }, { inventoryId: 'a-2', quantity: 2 },
  ], articleGroup: 'Overig' },
  { id: 'household:b', quantity: 4, inventoryEntries: [{ inventoryId: 'b-1', quantity: 4 }] },
]
const optimistic = applyInventoryRowQuantity(initialRows, 'household:a', 'a-1', 4)
assert.equal(optimistic[0].quantity, 6)
assert.equal(optimistic[0].inventoryEntries[0].quantity, 4)
assert.equal(optimistic[0].articleGroup, 'Overig')
assert.strictEqual(optimistic[1], initialRows[1])
assert.equal(initialRows[0].quantity, 5)
assert.equal(applyInventoryRowQuantity(initialRows, 'household:b', 'b-1', 0).length, 1)
assert.strictEqual(applyInventoryRowQuantity(initialRows, 'household:a', 'a-1', -1), initialRows)
assert.match(mobileSource, /setRows\(\(current\) => applyInventoryRowQuantity/)
assert.match(mobileSource, /setRows\(previousRows\)/)
assert.doesNotMatch(mobileSource, /setRows\(await loadMobileInventory\(\)\)/)
assert.doesNotMatch(mobileSource, /variant: 'success'/)

// A pre-existing locationless row remains editable after Waar Inhuis is enabled.
assert.doesNotMatch(mobileSource, /requiresStockLocationAssignment|warnAssignLocationFirst/)
assert.match(mobileSource, /buildQuickInventoryMutation\(row, direction\)/)
assert.match(mobileSource, /buildExactInventoryMutation\(row, nextQuantity\)/)

console.log('MOBILE_VOORRAAD_CONTRACT_GREEN')
