const LOGIN_MESSAGE_KEY = 'rezzerv_login_message'
const PLATFORM_SUPERUSER_EMAIL = 'supergebruiker@rezzerv.local'
const FRONTTEAM_EXTERNAL_DATABASES_PERMISSION = 'frontteam.external_databases.access'

let currentSessionContext = null
let sessionRequest = null

function safeWindow() {
  return typeof window !== 'undefined' ? window : null
}

function normalizeSessionContext(context) {
  if (!context || typeof context !== 'object') return null
  return {
    user_id: context.user_id || '',
    email: context.email || '',
    active_household_id: context.active_household_id || '',
    active_household_name: context.active_household_name || '',
    role: context.role || '',
    display_role: context.display_role || context.role || '',
    membership_count: Number(context.membership_count || 0),
    can_switch_households: Boolean(context.can_switch_households),
    memberships: Array.isArray(context.memberships) ? context.memberships : [],
    permissions: context.permissions && typeof context.permissions === 'object' ? context.permissions : {},
    member_permission_policies: context.member_permission_policies && typeof context.member_permission_policies === 'object' ? context.member_permission_policies : {},
    supported_permissions: Array.isArray(context.supported_permissions) ? context.supported_permissions : [],
    can_manage_member_permissions: Boolean(context.can_manage_member_permissions),
    can_manage_members: Boolean(context.can_manage_members),
    is_viewer: Boolean(context.is_viewer),
    is_frontteam_member: Boolean(context.is_frontteam_member),
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

export function getAuthHeaders() {
  return {}
}

export function readStoredAuthContext() {
  return currentSessionContext
}

export function storeAuthContext(context) {
  currentSessionContext = normalizeSessionContext(context)
  removeLegacyAuthStorage()
  return currentSessionContext
}

export function markAuthCheckedForToken() {}

export function isTokenAlreadyValidated() {
  return Boolean(currentSessionContext)
}

export function getLoginMessage() {
  try {
    const value = window.sessionStorage.getItem(LOGIN_MESSAGE_KEY) || ''
    if (value) window.sessionStorage.removeItem(LOGIN_MESSAGE_KEY)
    return value
  } catch {
    return ''
  }
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
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
    .then(async (response) => {
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = buildAuthErrorMessage(response.status, data?.detail || 'Je sessie is verlopen. Log opnieuw in.')
        const error = new Error(message)
        error.status = response.status
        throw error
      }
      return storeAuthContext(data)
    })
    .finally(() => {
      sessionRequest = null
    })

  return sessionRequest
}

export async function logoutServerSession() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
  } finally {
    clearAuthSession()
  }
}

export async function fetchJsonWithAuth(url, options = {}) {
  const { headers: optionHeaders = {}, cache = 'no-store', ...restOptions } = options
  const mergedHeaders = { ...optionHeaders }
  const hasBody = restOptions.body !== undefined && restOptions.body !== null
  if (hasBody && !mergedHeaders['Content-Type']) mergedHeaders['Content-Type'] = 'application/json'
  delete mergedHeaders.Authorization
  delete mergedHeaders.authorization

  const response = await fetch(url, {
    ...restOptions,
    credentials: 'include',
    headers: mergedHeaders,
    cache,
  })
  if (response.status === 401) {
    redirectToLogin('Je sessie is verlopen. Log opnieuw in.')
    const error = new Error('Je sessie is verlopen. Log opnieuw in.')
    error.status = 401
    throw error
  }
  return response
}

export function isHouseholdAdminFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return ['admin', 'owner', 'household.admin'].includes(
    String(source?.display_role || source?.role || '').trim().toLowerCase(),
  )
}

export function isPlatformSuperuserFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return String(source?.email || '').trim().toLowerCase() === PLATFORM_SUPERUSER_EMAIL
}

export function isFrontteamMemberFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return Boolean(
    source?.is_frontteam_member
    || source?.permissions?.[FRONTTEAM_EXTERNAL_DATABASES_PERMISSION],
  )
}

export function isHouseholdViewerFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return String(source?.display_role || source?.role || '').trim().toLowerCase() === 'viewer'
}

export function canCurrentUserPerform(permissionKey, context = null) {
  if (!permissionKey) return false
  const source = context || readStoredAuthContext()
  return Boolean(source?.permissions?.[permissionKey])
}
