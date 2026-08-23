import assert from 'node:assert/strict'
import { buildSettingsNavigation } from '../src/features/settings/settingsNavigation.js'

function keys(navigation) {
  return navigation.tiles.map((tile) => tile.key)
}

{
  const navigation = buildSettingsNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: null,
      product_configuration: null,
    },
  })
  assert.equal(navigation.mode, 'legacy')
  assert.deepEqual(keys(navigation), [
    'article-details',
    'article-groups',
    'privacy-data-sharing',
    'locations',
    'store-import',
    'household',
    'authorizations',
    'household-automation',
    'almost-out',
  ])
}

{
  const navigation = buildSettingsNavigation({
    onboarding: {
      primary_use_case: 'inhuis_halen',
      product_configuration: {
        inventory_tracking_level: 'quantity',
        location_tracking_level: 'none',
        shopping_enabled: true,
        almost_out_enabled: true,
        receipt_processing_enabled: true,
      },
    },
  })
  assert.equal(navigation.mode, 'dynamic')
  assert.deepEqual(keys(navigation), [
    'article-details',
    'article-groups',
    'privacy-data-sharing',
    'store-import',
    'household',
    'authorizations',
    'household-automation',
    'almost-out',
  ])
}

{
  const navigation = buildSettingsNavigation({
    onboarding: {
      primary_use_case: 'inhuis_halen',
      product_configuration: {
        inventory_tracking_level: 'none',
        location_tracking_level: 'none',
        shopping_enabled: true,
        almost_out_enabled: false,
        receipt_processing_enabled: false,
      },
    },
  })
  assert.deepEqual(keys(navigation), [
    'privacy-data-sharing',
    'store-import',
    'household',
    'authorizations',
  ])
}

{
  const navigation = buildSettingsNavigation({
    onboarding: {
      primary_use_case: 'wat_inhuis',
      product_configuration: {
        inventory_tracking_level: 'quantity',
        location_tracking_level: 'global',
        shopping_enabled: false,
        almost_out_enabled: true,
        receipt_processing_enabled: false,
      },
    },
  })
  assert.deepEqual(keys(navigation), [
    'article-details',
    'article-groups',
    'privacy-data-sharing',
    'locations',
    'household',
    'authorizations',
    'household-automation',
    'almost-out',
  ])
}

{
  const configuration = {
    inventory_tracking_level: 'presence',
    location_tracking_level: 'exact',
    shopping_enabled: false,
    almost_out_enabled: true,
    receipt_processing_enabled: true,
  }
  const navigation = buildSettingsNavigation({
    onboarding: {
      primary_use_case: 'waar_inhuis',
      product_configuration: configuration,
    },
  })
  assert.deepEqual(keys(navigation), [
    'article-details',
    'article-groups',
    'privacy-data-sharing',
    'locations',
    'store-import',
    'household',
    'authorizations',
    'almost-out',
  ])

  const sameCapabilitiesDifferentStart = buildSettingsNavigation({
    onboarding: {
      primary_use_case: 'inhuis_halen',
      product_configuration: configuration,
    },
  })
  assert.deepEqual(keys(sameCapabilitiesDifferentStart), keys(navigation))
}

console.log('DYNAMIC_SETTINGS_NAVIGATION_CONTRACT_GREEN')
