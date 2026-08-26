const LOGIN_MESSAGE_KEY = 'rezzerv_login_message'
const FRONTTEAM_EXTERNAL_DATABASES_PERMISSION = 'frontteam.external_databases.access'
const SYSTEM_HOUSEHOLD_ACCESS_PERMISSION = 'platform.system_household.access'
const REFERENCE_READ_CACHE_TTL_MS = 60_000

let currentSessionContext = null
let sessionRequest = null
const referenceReadCache = new Map()

function safeWindow() {
  return typeof window !== 'undefined' ? window : null
}

function normalizeRoleValue(value) {
  return String(value || '').trim().toLowerCase()
}

function normalizeContextType(value) {
  const normalized = String(value || '').trim().toLowerCase()
  return ['regular', 'system', 'none'].includes(normalized) ? normalized : ''
}

function normalizedRequestMethod(options = {}) {
  return String(options?.method || 'GET').trim().toUpperCase() || 'GET'
}

function normalizedRequestUrl(url) {
  return String(url || '').split('?')[0]
}

function referenceReadCacheKey(url, method) {
  if (method !== 'GET') return ''
  const normalizedUrl = normalizedRequestUrl(url)
  if (!['/api/spaces', '/api/sublocations'].includes(normalizedUrl)) return ''
  const householdId = String(currentSessionContext?.active_household_id || '').trim()
  return householdId ? `${normalizedUrl}::${householdId}` : ''
}

function invalidateReferenceReadCache(url, method) {
  if (method === 'GET') return
  const normalizedUrl = normalizedRequestUrl(url)
  const changesLocations = normalizedUrl === '/api/spaces'
    || normalizedUrl.startsWith('/api/spaces/')
    || normalizedUrl === '/api/sublocations'
    || normalizedUrl.startsWith('/api/sublocations/')
  if (changesLocations) referenceReadCache.clear()
}

function getCachedReferenceResponse(cacheKey) {
  if (!cacheKey) return null
  const cached = referenceReadCache.get(cacheKey)
  if (!cached) return null
  if (cached.expiresAt <= Date.now()) {
    referenceReadCache.delete(cacheKey)
    return null
  }
  return cached.response.clone()
}

function cacheReferenceResponse(cacheKey, response) {
  if (!cacheKey || !response?.ok) return
  referenceReadCache.set(cacheKey, {
    expiresAt: Date.now() + REFERENCE_READ_CACHE_TTL_MS,
    response: response.clone(),
  })
}

const NON_VIEWER_HOUSEHOLD_ROLES = new Set([
  'admin',
  'owner',
  'lid',
  'member',
  'advanced_member',
  'geavanceerd lid',
  'frontteam',
  'frontteamlid',
  'household.admin',
  'household.owner',
  'household.member',
  'household.advanced_member',
  'household.frontteam',
])

export function normalizeHouseholdAccessContext(context) {
  if (!context || typeof context !== 'object') return context
  const displayRole = normalizeRoleValue(context.display_role)
  const technicalRole = normalizeRoleValue(context.role || context.membership_role)
  const hasNonViewerRole = NON_VIEWER_HOUSEHOLD_ROLES.has(displayRole)
    || NON_VIEWER_HOUSEHOLD_ROLES.has(technicalRole)
  const canProcessReceipts = Boolean(context.permissions?.['receipts.process']) || hasNonViewerRole
  return {
    ...context,
    is_viewer: hasNonViewerRole ? false : Boolean(context.is_viewer || displayRole === 'viewer' || technicalRole === 'viewer'),
    can_process_receipts: canProcessReceipts,
  }
}

function normalizeSessionContext(context) {
  if (!context || typeof context !== 'object') return null
  const normalizedHouseholdContext = normalizeHouseholdAccessContext(context)
  const contextType = normalizeContextType(normalizedHouseholdContext.context_type)
  const hasNoHouseholdContext = contextType === 'none'
  return {
    user_id: normalizedHouseholdContext.user_id || normalizedHouseholdContext.user?.id || '',
    email: normalizedHouseholdContext.email || normalizedHouseholdContext.user?.email || '',
    active_household_id: hasNoHouseholdContext ? null : normalizedHouseholdContext.active_household_id ?? '',
    active_household_name: normalizedHouseholdContext.active_household_name || '',
    context_type: contextType,
    role: hasNoHouseholdContext ? null : normalizedHouseholdContext.role || '',
    display_role: hasNoHouseholdContext ? null : normalizedHouseholdContext.display_role || normalizedHouseholdContext.role || '',
    membership_count: Number(normalizedHouseholdContext.membership_count || 0),
    can_switch_households: Boolean(normalizedHouseholdContext.can_switch_households),
    memberships: Array.isArray(normalizedHouseholdContext.memberships) ? normalizedHouseholdContext.memberships : [],
    permissions: normalizedHouseholdContext.permissions && typeof normalizedHouseholdContext.permissions === 'object' ? normalizedHouseholdContext.permissions : {},
    member_permission_policies: normalizedHouseholdContext.member_permission_policies && typeof normalizedHouseholdContext.member_permission_policies === 'object' ? normalizedHouseholdContext.member_permission_policies : {},
    supported_permissions: Array.isArray(normalizedHouseholdContext.supported_permissions) ? normalizedHouseholdContext.supported_permissions : [],
    can_manage_member_permissions: Boolean(normalizedHouseholdContext.can_manage_member_permissions),
    can_manage_members: Boolean(normalizedHouseholdContext.can_manage_members),
    is_viewer: Boolean(normalizedHouseholdContext.is_viewer),
    can_process_receipts: Boolean(normalizedHouseholdContext.can_process_receipts),
    is_frontteam: Boolean(normalizedHouseholdContext.is_frontteam || normalizedHouseholdContext.is_frontteam_member),
    is_platform_superuser: Boolean(normalizedHouseholdContext.is_platform_superuser),
  }
}

function removeLegacyAuthStorage() {
  try {
    window.localStorage.removeItem('rezzerv_token')
    window.localStorage.removeItem('rezzerv_user_email')
    window.localStorage.removeItem('rezzerv_household_name')
    window.localStorage.removeItem('rezzerv_auth_context')
  } catch {}
  try {
    window.sessionStorage.removeItem('rezzerv_auth_checked_token')
  } catch {}
}

export function getStoredToken() {
  return ''
}
export function getAuthHeaders() { return {} }
export function readStoredAuthContext() { return currentSessionContext }

export function storeAuthContext(context) {
  const nextContext = normalizeSessionContext(context)
  const previousHouseholdId = String(currentSessionContext?.active_household_id || '').trim()
  const nextHouseholdId = String(nextContext?.active_household_id || '').trim()
  if (previousHouseholdId !== nextHouseholdId) referenceReadCache.clear()
  currentSessionContext = nextContext
  removeLegacyAuthStorage()
  return currentSessionContext
}

export function markAuthCheckedForToken() {}
export function isTokenAlreadyValidated() { return Boolean(currentSessionContext) }

export function getLoginMessage() {
  try {
    const value = window.sessionStorage.getItem(LOGIN_MESSAGE_KEY) || ''
    if (value) window.sessionStorage.removeItem(LOGIN_MESSAGE_KEY)
    return value
  } catch { return '' }
}

export function setLoginMessage(message) {
  try {
    if (!message) {
      window.sessionStorage.removeItem(LOGIN_MESSAGE_KEY)
      return
    }
    window.sessionStorage.setItem(LOGIN_MESSAGE_KEY, message)
  } catch {}
}

export function clearAuthSession(message = '') {
  currentSessionContext = null
  sessionRequest = null
  referenceReadCache.clear()
  removeLegacyAuthStorage()
  setLoginMessage(message)
}

export function redirectToLogin(message = '') {
  clearAuthSession(message)
  const win = safeWindow()
  if (win) win.location.replace('/login')
}

function buildAuthErrorMessage(status, fallback) {
  if (status === 401) return 'Je sessie is verlopen. Log opnieuw in.'
  if (status === 403) return fallback || 'Je hebt geen toegang tot deze actie.'
  return fallback || 'Verzoek mislukt.'
}

export async function fetchAuthContext({ force = false } = {}) {
  removeLegacyAuthStorage()
  if (!force && currentSessionContext) return currentSessionContext
  if (!force && sessionRequest) return sessionRequest
  sessionRequest = fetch('/api/session', {
    method: 'GET', credentials: 'include', headers: { Accept: 'application/json' }, cache: 'no-store',
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const message = buildAuthErrorMessage(response.status, data?.detail || 'Je sessie is verlopen. Log opnieuw in.')
      const error = new Error(message)
      error.status = response.status
      throw error
    }
    return storeAuthContext(data)
  }).finally(() => { sessionRequest = null })
  return sessionRequest
}

export async function logoutServerSession() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST', credentials: 'include', headers: { Accept: 'application/json' }, cache: 'no-store',
    })
  } finally { clearAuthSession() }
}

function jsonResponseFrom(response, payload) {
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify(payload), {
    status: response.status, statusText: response.statusText, headers,
  })
}

export async function fetchJsonWithAuth(url, options = {}) {
  const { headers: optionHeaders = {}, cache = 'no-store', ...restOptions } = options
  const mergedHeaders = { ...optionHeaders }
  const hasBody = restOptions.body !== undefined && restOptions.body !== null
  if (hasBody && !mergedHeaders['Content-Type']) mergedHeaders['Content-Type'] = 'application/json'
  delete mergedHeaders.Authorization
  delete mergedHeaders.authorization

  const requestMethod = normalizedRequestMethod(restOptions)
  const normalizedUrl = normalizedRequestUrl(url)
  const cacheKey = referenceReadCacheKey(url, requestMethod)
  const cachedResponse = getCachedReferenceResponse(cacheKey)
  if (cachedResponse) return cachedResponse
  invalidateReferenceReadCache(url, requestMethod)

  const response = await fetch(url, {
    ...restOptions, credentials: 'include', headers: mergedHeaders, cache,
  })
  if (response.status === 401) {
    redirectToLogin('Je sessie is verlopen. Log opnieuw in.')
    const error = new Error('Je sessie is verlopen. Log opnieuw in.')
    error.status = 401
    throw error
  }

  cacheReferenceResponse(cacheKey, response)

  if (response.ok && normalizedUrl === '/api/household') {
    try {
      const payload = await response.clone().json()
      const normalizedPayload = normalizeHouseholdAccessContext(payload)
      if (JSON.stringify(payload) !== JSON.stringify(normalizedPayload)) {
        return jsonResponseFrom(response, normalizedPayload)
      }
    } catch {}
  }
  return response
}

export function isHouseholdAdminFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return Boolean(source?.permissions?.['admin.access']) || [
    'admin', 'owner', 'frontteam', 'frontteamlid',
    'household.admin', 'household.owner', 'household.frontteam',
  ].includes(String(source?.display_role || source?.role || '').trim().toLowerCase())
}

export function isPlatformSuperuserFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return Boolean(
    source?.is_platform_superuser
    || (
      source?.context_type === 'system'
      && source?.permissions?.[SYSTEM_HOUSEHOLD_ACCESS_PERMISSION]
    )
  )
}

export function isFrontteamMemberFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return Boolean(
    isPlatformSuperuserFromContext(source)
    || source?.is_frontteam
    || source?.permissions?.[FRONTTEAM_EXTERNAL_DATABASES_PERMISSION],
  )
}

export function isHouseholdViewerFromContext(context = null) {
  const source = normalizeHouseholdAccessContext(context || readStoredAuthContext())
  return Boolean(source?.is_viewer)
}

export function canCurrentUserPerform(permissionKey, context = null) {
  if (!permissionKey) return false
  const source = context || readStoredAuthContext()
  return Boolean(source?.permissions?.[permissionKey])
}
