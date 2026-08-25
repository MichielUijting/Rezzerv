export const SETTINGS_SECTIONS = [
  {
    key: 'account',
    title: 'Mijn account',
    description: 'Persoonlijke voorkeuren en privacy.',
  },
  {
    key: 'household',
    title: 'Huishouden & samen gebruiken',
    description: 'Beheer je huishouden, leden en rollen.',
  },
  {
    key: 'usage',
    title: 'Gebruik & inrichting',
    description: 'Pas Inhuis aan op de mogelijkheden die je huishouden gebruikt.',
  },
  {
    key: 'help',
    title: 'Hulp & informatie',
    description: 'Hulp en informatie over Inhuis.',
  },
]

const REGULAR_SETTINGS_CONTEXTS = ['regular']

export const SETTINGS_ROOT_POLICY = {
  allowedContexts: REGULAR_SETTINGS_CONTEXTS,
  allowViewer: true,
}

const SETTINGS_TILES = [
  {
    key: 'account',
    title: 'Mijn account',
    description: 'E-mailadres en wachtwoord',
    to: '/instellingen/mijn-account',
    relevance: 'always',
    section: 'account',
    scope: 'personal',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: true,
  },
  {
    key: 'capabilities',
    title: 'Wat wil je met Inhuis doen?',
    description: 'Voeg later extra mogelijkheden toe zonder opnieuw te beginnen',
    to: '/instellingen/mogelijkheden',
    permission: 'household_settings.manage',
    relevance: 'always',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'article-details',
    title: 'Artikeldetails',
    description: 'Veldzichtbaarheid',
    to: '/instellingen/artikeldetails/veldzichtbaarheid',
    relevance: 'inventory',
    section: 'account',
    scope: 'personal',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: true,
  },
  {
    key: 'article-groups',
    title: 'Artikelgroepen',
    description: 'Beheer je eigen indeling van voorraadartikelen',
    to: '/instellingen/artikelgroepen',
    permission: 'article_groups.manage',
    relevance: 'inventory',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'privacy-data-sharing',
    title: 'Privacy & Datadeling',
    description: 'Persoonlijke toestemming per gebruiker · standaard alles uit',
    to: '/instellingen/privacy-datadeling',
    relevance: 'always',
    section: 'account',
    scope: 'personal',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: true,
  },
  {
    key: 'locations',
    title: 'Locaties',
    description: 'Beheer locaties en sublocaties voor Voorraad, Kassa en Incidentele aankoop',
    to: '/instellingen/locaties',
    permission: 'locations.manage',
    relevance: 'locations',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'store-import',
    title: 'Winkelimport',
    description: 'Vereenvoudigingsniveau voor het huishouden',
    to: '/instellingen/winkelimport',
    permission: 'household_settings.manage',
    relevance: 'shopping-or-receipts',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'household',
    title: 'Huishouden',
    description: 'Naam, leden en rollen beheren',
    to: '/instellingen/huishouden',
    permission: 'household_settings.manage',
    relevance: 'always',
    section: 'household',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'authorizations',
    title: 'Autorisaties',
    description: 'Bekijk welke mogelijkheden bij elke rol horen',
    to: '/instellingen/huishouden/autorisaties',
    relevance: 'always',
    section: 'household',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: true,
  },
  {
    key: 'household-automation',
    title: 'Huishoudautomatisering',
    description: 'Slim afboeken bij herhaalaankoop',
    to: '/instellingen/huishoudautomatisering',
    permission: 'household_settings.manage',
    relevance: 'quantity-inventory',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'almost-out',
    title: 'Bijna op voorspelling',
    description: 'Huishoudbrede bijna-op voorspelling en regelprioriteit',
    to: '/instellingen/bijna-op-voorspelling',
    permission: 'household_settings.manage',
    relevance: 'almost-out',
    section: 'usage',
    scope: 'household',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: false,
  },
  {
    key: 'help-about',
    title: 'Hulp & Over',
    description: 'Versie, ondersteuning en privacy',
    to: '/instellingen/hulp-over',
    relevance: 'always',
    section: 'help',
    scope: 'personal',
    allowedContexts: REGULAR_SETTINGS_CONTEXTS,
    allowViewer: true,
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

function buildSections(tiles) {
  return SETTINGS_SECTIONS
    .map((section) => ({
      ...section,
      tiles: tiles.filter((tile) => tile.section === section.key),
    }))
    .filter((section) => section.tiles.length > 0)
}

export function buildSettingsNavigation({ onboarding } = {}) {
  const configuration = normalizedConfiguration(onboarding)
  const mode = configuration ? 'dynamic' : 'legacy'
  const tiles = configuration
    ? SETTINGS_TILES.filter((tile) => isRelevant(tile, configuration))
    : SETTINGS_TILES

  return {
    mode,
    tiles,
    sections: buildSections(tiles),
  }
}

export function getSettingsTile(key) {
  return SETTINGS_TILES.find((tile) => tile.key === key) || null
}

export { SETTINGS_TILES }
