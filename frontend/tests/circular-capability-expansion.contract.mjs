import assert from 'node:assert/strict'
import fs from 'node:fs'
import { buildExpansionQuestions, isUseCaseActive } from '../src/features/settings/capabilityExpansion.js'
import { buildSettingsNavigation } from '../src/features/settings/settingsNavigation.js'

const inhuisConfiguration = {
  inventory_tracking_level: 'quantity',
  location_tracking_level: 'none',
  shopping_enabled: true,
  almost_out_enabled: true,
  almost_out_notifications_enabled: true,
  receipt_processing_enabled: true,
  recipes_enabled: false,
  unpacking_enabled: false,
}

{
  const questions = buildExpansionQuestions('wat_inhuis', inhuisConfiguration)
  assert.equal(questions.inventoryLevel, false)
  assert.equal(questions.globalLocations, true)
  assert.equal(questions.almostOut, false)
  assert.equal(questions.shopping, false)
}

{
  const questions = buildExpansionQuestions('waar_inhuis', {
    ...inhuisConfiguration,
    location_tracking_level: 'global',
  })
  assert.equal(questions.locationRefinement, false, 'Waar Inhuis mag geen tweede locatie-invoer tonen')
  assert.equal(questions.needsFirstMainLocation, false, 'Locaties worden uitsluitend via Instellingen → Locaties ingericht')
  assert.equal(questions.preserveGlobalLocations, false)
  assert.equal(questions.receiptProcessing, false)
  assert.equal(questions.almostOut, false)
  assert.equal(questions.unpacking, true)
}

{
  const questions = buildExpansionQuestions('inhuis_halen', {
    inventory_tracking_level: 'presence',
    location_tracking_level: 'exact',
    shopping_enabled: false,
    almost_out_enabled: false,
    almost_out_notifications_enabled: false,
    receipt_processing_enabled: false,
    recipes_enabled: false,
    unpacking_enabled: true,
  })
  assert.equal(questions.inventoryUpgrade, true)
  assert.equal(questions.almostOutNotifications, true)
  assert.equal(questions.receiptProcessing, true)
  assert.equal(questions.recipes, true)
}

assert.equal(isUseCaseActive(['inhuis_halen', 'wat_inhuis'], 'wat_inhuis'), true)
assert.equal(isUseCaseActive(['inhuis_halen'], 'waar_inhuis'), false)

for (const onboarding of [
  { product_configuration: null },
  { product_configuration: inhuisConfiguration },
]) {
  const navigation = buildSettingsNavigation({ onboarding })
  const capabilityTile = navigation.tiles.find((tile) => tile.key === 'capabilities')
  assert.ok(capabilityTile, 'Wat wil je met Inhuis doen? moet altijd in Instellingen staan')
  assert.equal(capabilityTile.permission, 'household_settings.manage')
}

const articleStockSource = fs.readFileSync(
  new URL('../src/features/articles/tabs/ArticleStockTab.jsx', import.meta.url),
  'utf8',
)
assert.match(articleStockSource, /Nog geen locatie/, 'Locatie-loze voorraad moet herkenbaar blijven')
assert.match(articleStockSource, /Locatie toewijzen/, 'Locatie-loze voorraad moet toewijsbaar zijn')
assert.match(
  articleStockSource,
  /inventory-transfers/,
  'Toewijzen moet de canonical transfer-flow gebruiken zodat gedeeltelijk splitsen mogelijk blijft',
)
assert.match(
  articleStockSource,
  /Instellingen → Locaties/,
  'Locaties moeten vanuit de voorraadflow naar de canonical instellingenplek verwijzen',
)

const workflowPage = fs.readFileSync(
  new URL('../src/features/settings/SettingsCapabilitiesPage.jsx', import.meta.url),
  'utf8',
)
assert.match(workflowPage, /Voorraadlocaties en Uitpakken/)
assert.match(workflowPage, /workflow-location-level/)
assert.match(workflowPage, /workflow-unpacking-enabled/)
assert.match(workflowPage, /workflow-preferences-save/)
assert.ok(workflowPage.includes('/api/onboarding/workflow-preferences'))
assert.match(workflowPage, /household-configuration-changed/)
const workflowRoute = fs.readFileSync(
  new URL('../../backend/app/api/household_capability_expansion_routes.py', import.meta.url),
  'utf8',
)
assert.ok(workflowRoute.includes('@router.put("/api/onboarding/workflow-preferences")'))
assert.ok(workflowRoute.includes('_require_manage_context()'))
assert.match(workflowRoute, /save_household_workflow_preferences/)
const mobile = fs.readFileSync(new URL('../src/app/MobileAppChrome.jsx', import.meta.url), 'utf8')
assert.match(mobile, /inhuis:household-configuration-changed/)

console.log('CIRCULAR_CAPABILITY_EXPANSION_FRONTEND_GREEN')
