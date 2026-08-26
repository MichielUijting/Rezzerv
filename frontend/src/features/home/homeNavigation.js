const LEGACY_TILES = [
  { key: 'meldingen', label: 'Meldingen', icon: '✉️', clickable: true },
  { key: 'bijna-op', label: 'Bijna op', icon: '📉', clickable: true },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒', clickable: true },
  { key: 'prognoses', label: 'Prognoses', icon: '📊', clickable: false },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁', clickable: false },
  { key: 'voorraad', label: 'Voorraad', icon: '📦', clickable: true },
  { key: 'productgroepen', label: 'Productgroepen', icon: '🧩', clickable: true },
  { key: 'kassabonnen', label: 'Uitpakken', icon: '🧾', clickable: true },
  { key: 'kassa', label: 'Kassa', icon: '🧾', clickable: true },
  { key: 'spaartegoeden', label: 'Spaartegoeden', icon: '🪙', clickable: true },
  { key: 'externe-databases', label: 'Externe databases', icon: '🗄️', clickable: true },
  { key: 'catalogus', label: 'Catalogus', icon: 'CAT', clickable: true },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳', clickable: false },
  { key: 'recepten', label: 'Recepten', icon: '🍳', clickable: false },
  { key: 'bestellen', label: 'Bestellen', icon: '📋', clickable: false },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳', clickable: false },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️', clickable: true },
  { key: 'admin', label: 'Admin', icon: '🛠️', clickable: true },
  { key: 'superuser', label: 'Superuser', icon: '🛡️', clickable: true },
]

const LOCATIONS_TILE = {
  key: 'locaties',
  label: 'Locaties',
  icon: '📍',
  clickable: true,
}

function isVisible(tile, visibility) {
  if (tile.key === 'meldingen') return !visibility.isPlatformSuperuser
  if (tile.key === 'admin') return visibility.canOpenAdmin
  if (tile.key === 'externe-databases') return visibility.canOpenExternalDatabases
  if (tile.key === 'superuser') return visibility.isPlatformSuperuser
  if (tile.key === 'locaties') return visibility.canManageLocations
  return true
}

function uniqueTiles(tiles) {
  const seen = new Set()
  return tiles.filter((tile) => {
    if (!tile || seen.has(tile.key)) return false
    seen.add(tile.key)
    return true
  })
}

function findTile(key) {
  if (key === LOCATIONS_TILE.key) return LOCATIONS_TILE
  return LEGACY_TILES.find((tile) => tile.key === key) || null
}

function primaryKeysFor(onboarding) {
  const configuration = onboarding?.product_configuration
  if (!configuration || typeof configuration !== 'object') return []

  const primaryUseCase = String(onboarding?.primary_use_case || '').trim().toLowerCase()
  const inventoryEnabled = String(configuration.inventory_tracking_level || '').trim().toLowerCase() !== 'none'
  const locationLevel = String(configuration.location_tracking_level || '').trim().toLowerCase()
  const almostOutEnabled = Boolean(configuration.almost_out_enabled)
  const shoppingEnabled = Boolean(configuration.shopping_enabled)
  const receiptProcessingEnabled = Boolean(configuration.receipt_processing_enabled)
  const unpackingEnabled = Boolean(configuration.unpacking_enabled)

  if (primaryUseCase === 'inhuis_halen') {
    return [
      almostOutEnabled ? 'bijna-op' : null,
      shoppingEnabled ? 'winkelen' : null,
      receiptProcessingEnabled ? 'kassa' : null,
    ].filter(Boolean)
  }

  if (primaryUseCase === 'wat_inhuis') {
    return [
      inventoryEnabled ? 'voorraad' : null,
      almostOutEnabled ? 'bijna-op' : null,
      shoppingEnabled ? 'winkelen' : null,
      receiptProcessingEnabled ? 'kassa' : null,
    ].filter(Boolean)
  }

  if (primaryUseCase === 'waar_inhuis') {
    return [
      inventoryEnabled ? 'voorraad' : null,
      locationLevel === 'exact' ? 'locaties' : null,
      unpackingEnabled ? 'kassabonnen' : null,
      receiptProcessingEnabled ? 'kassa' : null,
      almostOutEnabled ? 'bijna-op' : null,
      shoppingEnabled ? 'winkelen' : null,
    ].filter(Boolean)
  }

  return []
}

export function buildHomeNavigation({ onboarding, visibility }) {
  const safeVisibility = {
    canOpenAdmin: Boolean(visibility?.canOpenAdmin),
    canOpenExternalDatabases: Boolean(visibility?.canOpenExternalDatabases),
    isPlatformSuperuser: Boolean(visibility?.isPlatformSuperuser),
    canManageLocations: Boolean(visibility?.canManageLocations),
  }
  const configuration = onboarding?.product_configuration

  if (!configuration || typeof configuration !== 'object') {
    return {
      mode: 'legacy',
      primaryTiles: LEGACY_TILES.filter((tile) => isVisible(tile, safeVisibility)),
      moreTiles: [],
    }
  }

  const primaryTiles = uniqueTiles(
    primaryKeysFor(onboarding)
      .map(findTile)
      .filter((tile) => tile && tile.clickable && isVisible(tile, safeVisibility)),
  )
  const primaryKeys = new Set(primaryTiles.map((tile) => tile.key))
  const locationLevel = String(configuration.location_tracking_level || '').trim().toLowerCase()
  const dynamicCandidates = [
    ...LEGACY_TILES,
    ...(locationLevel !== 'none' ? [LOCATIONS_TILE] : []),
  ]
  const moreTiles = uniqueTiles(dynamicCandidates)
    .filter((tile) => tile.clickable)
    .filter((tile) => !primaryKeys.has(tile.key))
    .filter((tile) => isVisible(tile, safeVisibility))

  return {
    mode: 'dynamic',
    primaryTiles,
    moreTiles,
  }
}

export { LEGACY_TILES }
