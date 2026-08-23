let cachedKey = ''
let cachedState = null
let pendingRequest = null

function contextCacheKey(context) {
  const userId = String(context?.user_id || '').trim()
  const householdId = String(context?.active_household_id || '').trim()
  return userId && householdId ? `${userId}:${householdId}` : ''
}

function requestError(status, payload, fallback) {
  const error = new Error(payload?.detail || fallback)
  error.status = status
  return error
}

export function readHouseholdOnboarding(context) {
  const key = contextCacheKey(context)
  return key && key === cachedKey ? cachedState : null
}

export async function fetchHouseholdOnboarding(context, { force = false } = {}) {
  const key = contextCacheKey(context)
  if (!key) return null
  if (!force && key === cachedKey && cachedState) return cachedState
  if (!force && pendingRequest?.key === key) return pendingRequest.promise

  const promise = fetch('/api/onboarding', {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw requestError(response.status, payload, 'Onboardingstatus ophalen mislukt.')
    }
    cachedKey = key
    cachedState = payload
    return payload
  }).finally(() => {
    if (pendingRequest?.promise === promise) pendingRequest = null
  })

  pendingRequest = { key, promise }
  return promise
}

export async function selectPrimaryUseCase(context, primaryUseCase) {
  const key = contextCacheKey(context)
  if (!key) throw new Error('Geen actief huishouden beschikbaar.')

  const response = await fetch('/api/onboarding/primary-use-case', {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({ primary_use_case: primaryUseCase }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw requestError(response.status, payload, 'Gebruiksdoel opslaan mislukt.')
  }
  cachedKey = key
  cachedState = payload
  return payload
}

export async function completeInhuisHalenOnboarding(context, preferences) {
  const key = contextCacheKey(context)
  if (!key) throw new Error('Geen actief huishouden beschikbaar.')

  const response = await fetch('/api/onboarding/inhuis-halen', {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify(preferences),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw requestError(response.status, payload, 'Inhuis halen instellen mislukt.')
  }
  cachedKey = key
  cachedState = payload
  return payload
}

export function requiresInitialUseCase(state) {
  return Boolean(
    state?.initial_choice_required
    && state?.can_manage,
  )
}

export function requiresManagedOnboarding(state) {
  if (!state?.can_manage) return false
  if (state?.initial_choice_required) return true
  return Boolean(
    state?.onboarding_status === 'in_progress'
    && state?.onboarding_step === 'profile_follow_up'
    && state?.primary_use_case === 'inhuis_halen',
  )
}

export function isInhuisHalenFollowUp(state) {
  return Boolean(
    state?.onboarding_status === 'in_progress'
    && state?.onboarding_step === 'profile_follow_up'
    && state?.primary_use_case === 'inhuis_halen',
  )
}
