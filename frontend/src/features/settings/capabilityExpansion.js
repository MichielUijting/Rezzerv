export const CAPABILITY_USE_CASES = [
  {
    key: 'inhuis_halen',
    title: 'Inhuis halen',
    description: 'Boodschappen, bijna-op en aankopen makkelijker bijhouden.',
  },
  {
    key: 'wat_inhuis',
    title: 'Wat Inhuis',
    description: 'Bijhouden wat je in huis hebt en hoe gedetailleerd.',
  },
  {
    key: 'waar_inhuis',
    title: 'Waar Inhuis',
    description: 'Werken met locaties, sublocaties en Uitpakken.',
  },
]

function normalizedConfiguration(configuration) {
  return configuration && typeof configuration === 'object' ? configuration : {
    inventory_tracking_level: 'none',
    location_tracking_level: 'none',
    shopping_enabled: false,
    almost_out_enabled: false,
    almost_out_notifications_enabled: false,
    receipt_processing_enabled: false,
    recipes_enabled: false,
    unpacking_enabled: false,
  }
}

export function buildExpansionQuestions(useCase, configuration) {
  const config = normalizedConfiguration(configuration)
  const inventoryLevel = String(config.inventory_tracking_level || 'none').trim().toLowerCase()
  const locationLevel = String(config.location_tracking_level || 'none').trim().toLowerCase()

  if (useCase === 'inhuis_halen') {
    return {
      inventoryUpgrade: inventoryLevel !== 'quantity',
      almostOutNotifications: !Boolean(config.almost_out_notifications_enabled),
      receiptProcessing: !Boolean(config.receipt_processing_enabled),
      recipes: !Boolean(config.recipes_enabled),
    }
  }

  if (useCase === 'wat_inhuis') {
    return {
      inventoryLevel: inventoryLevel === 'none',
      globalLocations: locationLevel === 'none',
      almostOut: !Boolean(config.almost_out_enabled),
      shopping: !Boolean(config.shopping_enabled),
    }
  }

  if (useCase === 'waar_inhuis') {
    return {
      locationRefinement: locationLevel !== 'exact',
      needsFirstMainLocation: locationLevel === 'none',
      preserveGlobalLocations: locationLevel === 'global',
      unpacking: !Boolean(config.unpacking_enabled),
      receiptProcessing: !Boolean(config.receipt_processing_enabled),
      almostOut: !Boolean(config.almost_out_enabled),
    }
  }

  return {}
}

export function isUseCaseActive(activeUseCases, useCase) {
  return Array.isArray(activeUseCases) && activeUseCases.includes(useCase)
}
