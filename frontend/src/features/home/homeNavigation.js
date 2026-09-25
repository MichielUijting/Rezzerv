import { FEATURE_GERECHTEN, isFeatureEnabled } from '../platform/featureAvailability.js'

const LEGACY_TILES = [
  { key: 'meldingen', label: 'Meldingen', icon: '✉️', clickable: true },
  { key: 'bijna-op', label: 'Bijna op', icon: '📉', clickable: true },
  { key: 'winkelen', label: 'Boodschappen', icon: '🛒', clickable: true },
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
  { key: 'recepten', label: 'Gerechten', icon: '🍳', clickable: false, feature: FEATURE_GERECHTEN },
  { key: 'bestellen', label: 'Bestellen', icon: '📋', clickable: false },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳', clickable: false },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️', clickable: true },
  { key: 'admin', label: 'Admin', icon: '🛠️', clickable: true },
  { key: 'superuser', label: 'Superuser', icon: '🛡️', clickable: true },
]

const DYNAMIC_PRIMARY_USE_CASES = new Set(['inhuis_halen', 'wat_inhuis', 'waar_inhuis'])

function isGloballyAvailable(tile, actionButtons) {
  if (Object.hasOwn(actionButtons || {}, tile.key)) return actionButtons[tile.key] === true
  return true
}

function isVisible(tile, visibility) {
  if (tile.feature && !isFeatureEnabled(visibility.features, tile.feature)) return false
  if (!tile.feature && !isGloballyAvailable(tile, visibility.actionButtons)) return false
  if (tile.key === 'meldingen') return !visibility.isPlatformSuperuser
  if (tile.key === 'admin') return visibility.canOpenAdmin
  if (tile.key === 'externe-databases') return visibility.canOpenExternalDatabases
  if (tile.key === 'superuser') return visibility.isPlatformSuperuser
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

function sortTilesByActionOrder(tiles, actionOrder) {
  if (!Array.isArray(actionOrder) || actionOrder.length === 0) return tiles
  const rank = new Map(actionOrder.map((key, index) => [String(key), index]))
  return tiles
    .map((tile, originalIndex) => ({ tile, originalIndex }))
    .sort((a, b) => {
      const aRank = rank.has(a.tile.key) ? rank.get(a.tile.key) : 10000 + a.originalIndex
      const bRank = rank.has(b.tile.key) ? rank.get(b.tile.key) : 10000 + b.originalIndex
      return aRank - bRank || a.originalIndex - b.originalIndex
    })
    .map(({ tile }) => tile)
}

function findTile(key) {
  return LEGACY_TILES.find((tile) => tile.key === key) || null
}

function primaryKeysFor(onboarding) {
  const configuration = onboarding?.product_configuration
  if (!configuration || typeof configuration !== 'object') return []

  const primaryUseCase = String(onboarding?.primary_use_case || '').trim().toLowerCase()
  const inventoryEnabled = String(configuration.inventory_tracking_level || '').trim().toLowerCase() !== 'none'
  const almostOutEnabled = Boolean(configuration.almost_out_enabled)
  const shoppingEnabled = Boolean(configuration.shopping_enabled)
  const receiptProcessingEnabled = Boolean(configuration.receipt_processing_enabled)
  const unpackingEnabled = Boolean(configuration.unpacking_enabled)

  if (primaryUseCase === 'inhuis_halen') {
    return [almostOutEnabled ? 'bijna-op' : null, shoppingEnabled ? 'winkelen' : null, receiptProcessingEnabled ? 'kassa' : null].filter(Boolean)
  }
  if (primaryUseCase === 'wat_inhuis') {
    return [inventoryEnabled ? 'voorraad' : null, almostOutEnabled ? 'bijna-op' : null, shoppingEnabled ? 'winkelen' : null, receiptProcessingEnabled ? 'kassa' : null].filter(Boolean)
  }
  if (primaryUseCase === 'waar_inhuis') {
    return [inventoryEnabled ? 'voorraad' : null, unpackingEnabled ? 'kassabonnen' : null, receiptProcessingEnabled ? 'kassa' : null, almostOutEnabled ? 'bijna-op' : null, shoppingEnabled ? 'winkelen' : null].filter(Boolean)
  }
  return []
}

export function buildHomeNavigation({ onboarding, visibility, features = {}, actionButtons = {}, actionOrder = [] }) {
  const safeVisibility = {
    features,
    actionButtons,
    canOpenAdmin: Boolean(visibility?.canOpenAdmin),
    canOpenExternalDatabases: Boolean(visibility?.canOpenExternalDatabases),
    isPlatformSuperuser: Boolean(visibility?.isPlatformSuperuser),
  }
  const configuration = onboarding?.product_configuration
  const primaryUseCase = String(onboarding?.primary_use_case || '').trim().toLowerCase()

  if (!configuration || typeof configuration !== 'object' || !DYNAMIC_PRIMARY_USE_CASES.has(primaryUseCase)) {
    return {
      mode: 'legacy',
      primaryTiles: sortTilesByActionOrder(
        LEGACY_TILES.filter((tile) => isVisible(tile, safeVisibility)),
        actionOrder,
      ),
      moreTiles: [],
    }
  }

  const primaryKeys = primaryKeysFor(onboarding)
  if (safeVisibility.canOpenAdmin) primaryKeys.push('instellingen')

  const primaryTiles = sortTilesByActionOrder(uniqueTiles(
    primaryKeys
      .map(findTile)
      .filter((tile) => tile && tile.clickable && isVisible(tile, safeVisibility)),
  ), actionOrder)
  const visiblePrimaryKeys = new Set(primaryTiles.map((tile) => tile.key))
  const moreTiles = sortTilesByActionOrder(
    uniqueTiles(LEGACY_TILES)
      .filter((tile) => tile.clickable)
      .filter((tile) => !visiblePrimaryKeys.has(tile.key))
      .filter((tile) => isVisible(tile, safeVisibility)),
    actionOrder,
  )

  return { mode: 'dynamic', primaryTiles, moreTiles }
}

export { LEGACY_TILES }
