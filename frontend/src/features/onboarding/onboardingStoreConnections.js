// Onboarding shows only retailers with an existing digital receipt transfer route.
// Browser bookmarklets are not evidence of a connected retailer account.
const ONBOARDING_RECEIPT_STORES = new Set(['ah', 'lidl', 'jumbo'])

export function shouldOfferStoreConnectionOnboarding(onboarding) {
  return onboarding?.onboarding_status === 'completed'
    && onboarding?.can_manage === true
    // Older completed onboarding responses can omit the optional configuration.
    // Absence is not an explicit decision to disable receipts.
    && onboarding?.product_configuration?.receipt_processing_enabled !== false
}

export function filterOnboardingReceiptStores(rows) {
  if (!Array.isArray(rows)) return []
  return rows.filter((row) => ONBOARDING_RECEIPT_STORES.has(String(row?.providerCode || '').toLowerCase()))
}


/** Persisted by the server against the authenticated active household. */
async function storeOnboardingRequest(path, method = 'GET', body) {
  const response = await fetch(path, {
    method, credentials: 'include', cache: 'no-store',
    headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Winkelonboarding opslaan of ophalen mislukt.')
  return payload
}

export function fetchStoreOnboardingProgress() {
  return storeOnboardingRequest('/api/onboarding/stores')
}

export function saveStoreOnboardingSelection(selected) {
  return storeOnboardingRequest('/api/onboarding/stores/selection', 'PUT', { selected })
}

export function saveStoreOnboardingResult(provider, result, queueId = null) {
  return storeOnboardingRequest('/api/onboarding/stores/result', 'POST', {
    provider, result, ...(queueId ? { queue_id: queueId } : {}),
  })
}

export function hasStoreOnboardingToResume(state) {
  return state?.available === true
    && Array.isArray(state.selected)
    && state.selected.some(code => state?.results?.[code] !== 'success')
}
