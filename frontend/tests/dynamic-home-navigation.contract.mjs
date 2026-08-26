import assert from 'node:assert/strict'
import { buildHomeNavigation } from '../src/features/home/homeNavigation.js'

const baseVisibility = {
  canOpenAdmin: false,
  canOpenExternalDatabases: false,
  isPlatformSuperuser: false,
  canManageLocations: true,
}

function keys(tiles) {
  return tiles.map((tile) => tile.key)
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: null,
      product_configuration: null,
    },
    visibility: baseVisibility,
  })
  assert.equal(navigation.mode, 'legacy')
  assert.ok(keys(navigation.primaryTiles).includes('voorraad'))
  assert.ok(keys(navigation.primaryTiles).includes('winkelen'))
  assert.ok(keys(navigation.primaryTiles).includes('prognoses'))
  assert.equal(navigation.moreTiles.length, 0)
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: null,
      product_configuration: {
        inventory_tracking_level: 'quantity',
        location_tracking_level: 'none',
        shopping_enabled: true,
        almost_out_enabled: true,
        receipt_processing_enabled: true,
        unpacking_enabled: true,
      },
    },
    visibility: {
      ...baseVisibility,
      canOpenAdmin: true,
    },
  })
  assert.equal(navigation.mode, 'legacy')
  assert.ok(keys(navigation.primaryTiles).includes('voorraad'))
  assert.ok(keys(navigation.primaryTiles).includes('kassa'))
  assert.ok(keys(navigation.primaryTiles).includes('prognoses'))
  assert.ok(keys(navigation.primaryTiles).includes('recepten'))
  assert.ok(keys(navigation.primaryTiles).includes('admin'))
  assert.equal(navigation.moreTiles.length, 0)
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: 'inhuis_halen',
      product_configuration: {
        inventory_tracking_level: 'quantity',
        location_tracking_level: 'none',
        shopping_enabled: true,
        almost_out_enabled: true,
        receipt_processing_enabled: true,
        unpacking_enabled: false,
      },
    },
    visibility: baseVisibility,
  })
  assert.equal(navigation.mode, 'dynamic')
  assert.deepEqual(keys(navigation.primaryTiles), ['bijna-op', 'winkelen', 'kassa'])
  assert.ok(keys(navigation.moreTiles).includes('voorraad'))
  assert.ok(!keys(navigation.moreTiles).includes('prognoses'))
  assert.ok(!keys(navigation.moreTiles).includes('locaties'))
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: 'wat_inhuis',
      product_configuration: {
        inventory_tracking_level: 'quantity',
        location_tracking_level: 'global',
        shopping_enabled: false,
        almost_out_enabled: true,
        receipt_processing_enabled: true,
        unpacking_enabled: false,
      },
    },
    visibility: baseVisibility,
  })
  assert.deepEqual(keys(navigation.primaryTiles), ['voorraad', 'bijna-op', 'kassa'])
  assert.ok(keys(navigation.moreTiles).includes('locaties'))
  assert.ok(keys(navigation.moreTiles).includes('winkelen'))
  assert.ok(!keys(navigation.moreTiles).includes('kassa'))
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: 'waar_inhuis',
      product_configuration: {
        inventory_tracking_level: 'presence',
        location_tracking_level: 'exact',
        shopping_enabled: false,
        almost_out_enabled: true,
        receipt_processing_enabled: true,
        unpacking_enabled: true,
      },
    },
    visibility: baseVisibility,
  })
  assert.deepEqual(
    keys(navigation.primaryTiles),
    ['voorraad', 'locaties', 'kassabonnen', 'kassa', 'bijna-op'],
  )
  assert.ok(!keys(navigation.moreTiles).some((key) => keys(navigation.primaryTiles).includes(key)))
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: 'waar_inhuis',
      product_configuration: {
        inventory_tracking_level: 'presence',
        location_tracking_level: 'exact',
        shopping_enabled: false,
        almost_out_enabled: false,
        receipt_processing_enabled: false,
        unpacking_enabled: false,
      },
    },
    visibility: { ...baseVisibility, canManageLocations: false },
  })
  assert.deepEqual(keys(navigation.primaryTiles), ['voorraad'])
  assert.ok(!keys(navigation.moreTiles).includes('locaties'))
}

{
  const navigation = buildHomeNavigation({
    onboarding: {
      onboarding_status: 'completed',
      primary_use_case: 'inhuis_halen',
      product_configuration: {
        inventory_tracking_level: 'none',
        location_tracking_level: 'none',
        shopping_enabled: true,
        almost_out_enabled: false,
        receipt_processing_enabled: false,
        unpacking_enabled: false,
      },
    },
    visibility: {
      canOpenAdmin: true,
      canOpenExternalDatabases: true,
      isPlatformSuperuser: false,
      canManageLocations: false,
    },
  })
  assert.deepEqual(keys(navigation.primaryTiles), ['winkelen'])
  assert.ok(keys(navigation.moreTiles).includes('admin'))
  assert.ok(keys(navigation.moreTiles).includes('externe-databases'))
  assert.ok(!keys(navigation.moreTiles).includes('superuser'))
}

console.log('DYNAMIC_HOME_NAVIGATION_CONTRACT_GREEN')
