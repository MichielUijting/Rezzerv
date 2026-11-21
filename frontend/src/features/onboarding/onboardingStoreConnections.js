// Onboarding shows only retailers with an existing digital receipt transfer route.
// Browser bookmarklets are not evidence of a connected retailer account.
const ONBOARDING_RECEIPT_STORES = new Set(['ah', 'lidl', 'jumbo'])

export function shouldOfferStoreConnectionOnboarding(onboarding) {
  return onboarding?.onboarding_status === 'completed'
    && onboarding?.can_manage === true
    && onboarding?.product_configuration?.receipt_processing_enabled === true
}

export function filterOnboardingReceiptStores(rows) {
  if (!Array.isArray(rows)) return []
  return rows.filter((row) => ONBOARDING_RECEIPT_STORES.has(String(row?.providerCode || '').toLowerCase()))
}
