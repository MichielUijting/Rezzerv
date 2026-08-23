import assert from 'node:assert/strict'
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
  assert.equal(questions.locationRefinement, true)
  assert.equal(questions.needsFirstMainLocation, false)
  assert.equal(questions.preserveGlobalLocations, true)
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

console.log('CIRCULAR_CAPABILITY_EXPANSION_FRONTEND_GREEN')
