const SETTINGS_TILES = [
  {
    key: 'article-details',
    title: 'Artikeldetails',
    description: 'Veldzichtbaarheid',
    to: '/instellingen/artikeldetails/veldzichtbaarheid',
    relevance: 'inventory',
  },
  {
    key: 'article-groups',
    title: 'Artikelgroepen',
    description: 'Beheer je eigen indeling van voorraadartikelen',
    to: '/instellingen/artikelgroepen',
    permission: 'article_groups.manage',
    relevance: 'inventory',
  },
  {
    key: 'privacy-data-sharing',
    title: 'Privacy & Datadeling',
    description: 'Persoonlijke toestemming per gebruiker · standaard alles uit',
    to: '/instellingen/privacy-datadeling',
    relevance: 'always',
  },
  {
    key: 'locations',
    title: 'Locaties',
    description: 'Beheer locaties en sublocaties voor Voorraad, Kassa en Incidentele aankoop',
    to: '/instellingen/locaties',
    permission: 'locations.manage',
    relevance: 'locations',
  },
  {
    key: 'store-import',
    title: 'Winkelimport',
    description: 'Vereenvoudigingsniveau voor het huishouden',
    to: '/instellingen/winkelimport',
    permission: 'household_settings.manage',
    relevance: 'shopping-or-receipts',
  },
  {
    key: 'household',
    title: 'Huishouden',
    description: 'Naam, leden en rollen beheren',
    to: '/instellingen/huishouden',
    permission: 'household_settings.manage',
    relevance: 'always',
  },
  {
    key: 'authorizations',
    title: 'Autorisaties',
    description: 'Bekijk welke mogelijkheden bij elke rol horen',
    to: '/instellingen/huishouden/autorisaties',
    relevance: 'always',
  },
  {
    key: 'household-automation',
    title: 'Huishoudautomatisering',
    description: 'Slim afboeken bij herhaalaankoop',
    to: '/instellingen/huishoudautomatisering',
    permission: 'household_settings.manage',
    relevance: 'quantity-inventory',
  },
  {
    key: 'almost-out',
    title: 'Bijna op voorspelling',
    description: 'Huishoudbrede bijna-op voorspelling en regelprioriteit',
    to: '/instellingen/bijna-op-voorspelling',
    permission: 'household_settings.manage',
    relevance: 'almost-out',
  },
]

function normalizedConfiguration(onboarding) {
  const configuration = onboarding?.product_configuration
  return configuration && typeof configuration === 'object' ? configuration : null
}

function isRelevant(tile, configuration) {
  if (tile.relevance === 'always') return true

  const inventoryLevel = String(configuration.inventory_tracking_level || '').trim().toLowerCase()
  const locationLevel = String(configuration.location_tracking_level || '').trim().toLowerCase()
  const inventoryEnabled = inventoryLevel !== 'none'

  if (tile.relevance === 'inventory') return inventoryEnabled
  if (tile.relevance === 'quantity-inventory') return inventoryLevel === 'quantity'
  if (tile.relevance === 'locations') return locationLevel !== 'none'
  if (tile.relevance === 'almost-out') return Boolean(configuration.almost_out_enabled)
  if (tile.relevance === 'shopping-or-receipts') {
    return Boolean(configuration.shopping_enabled || configuration.receipt_processing_enabled)
  }
  return false
}

export function buildSettingsNavigation({ onboarding } = {}) {
  const configuration = normalizedConfiguration(onboarding)
  if (!configuration) {
    return {
      mode: 'legacy',
      tiles: SETTINGS_TILES,
    }
  }

  return {
    mode: 'dynamic',
    tiles: SETTINGS_TILES.filter((tile) => isRelevant(tile, configuration)),
  }
}

export { SETTINGS_TILES }
