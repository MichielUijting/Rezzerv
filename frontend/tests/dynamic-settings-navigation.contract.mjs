import assert from 'node:assert/strict'
import {
  SETTINGS_ROOT_POLICY,
  SETTINGS_SECTIONS,
  SETTINGS_TILES,
  buildSettingsNavigation,
} from '../src/features/settings/settingsNavigation.js'

function keys(navigation) {
  return navigation.tiles.map((tile) => tile.key)
}

function sectionKeys(navigation) {
  return Object.fromEntries(
    navigation.sections.map((section) => [section.key, section.tiles.map((tile) => tile.key)]),
  )
}

assert.deepEqual(
  SETTINGS_SECTIONS.map((section) => section.key),
  ['account', 'household', 'usage', 'help'],
)
assert.deepEqual(SETTINGS_ROOT_POLICY.allowedContexts, ['regular'])
assert.equal(SETTINGS_ROOT_POLICY.allowViewer, true)
assert.equal(SETTINGS_TILES.length, 11)
for (const tile of SETTINGS_TILES) {
  assert.ok(['account', 'household', 'usage', 'help'].includes(tile.section))
  assert.ok(['personal', 'household'].includes(tile.scope))
  assert.deepEqual(tile.allowedContexts, ['regular'])
  assert.equal(typeof tile.allowViewer, 'boolean')
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
    'account',
    'capabilities',
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
  assert.deepEqual(sectionKeys(navigation), {
    account: ['account', 'article-details', 'privacy-data-sharing'],
    household: ['household', 'authorizations'],
    usage: [
      'capabilities',
      'article-groups',
      'locations',
      'store-import',
      'household-automation',
      'almost-out',
    ],
  })
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
    'account',
    'capabilities',
    'article-details',
    'article-groups',
    'privacy-data-sharing',
    'store-import',
    'household',
    'authorizations',
    'household-automation',
    'almost-out',
  ])
  assert.deepEqual(sectionKeys(navigation), {
    account: ['account', 'article-details', 'privacy-data-sharing'],
    household: ['household', 'authorizations'],
    usage: ['capabilities', 'article-groups', 'store-import', 'household-automation', 'almost-out'],
  })
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
    'account',
    'capabilities',
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
    'account',
    'capabilities',
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
    'account',
    'capabilities',
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
