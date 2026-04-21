const AUTH_CONTEXT_KEY = 'rezzerv_auth_context'
const AUTH_CHECKED_TOKEN_KEY = 'rezzerv_auth_checked_token'
const LOGIN_MESSAGE_KEY = 'rezzerv_login_message'

function safeWindow() {
  return typeof window !== 'undefined' ? window : null
}

export function getStoredToken() {
  try {
    return window.localStorage.getItem('rezzerv_token') || ''
  } catch {
    return ''
  }
}

export function getAuthHeaders() {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function readStoredAuthContext() {
  try {
    const raw = window.localStorage.getItem(AUTH_CONTEXT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function storeAuthContext(context) {
  if (!context || typeof context !== 'object') return null
  const normalized = {
    user_id: context.user_id || '',
    email: context.email || '',
    active_household_id: context.active_household_id || '',
    active_household_name: context.active_household_name || '',
    role: context.role || '',
    display_role: context.display_role || '',
    membership_count: Number(context.membership_count || 0),
    can_switch_households: Boolean(context.can_switch_households),
    memberships: Array.isArray(context.memberships) ? context.memberships : [],
    permissions: context.permissions && typeof context.permissions === 'object' ? context.permissions : {},
    member_permission_policies: context.member_permission_policies && typeof context.member_permission_policies === 'object' ? context.member_permission_policies : {},
    supported_permissions: Array.isArray(context.supported_permissions) ? context.supported_permissions : [],
    can_manage_member_permissions: Boolean(context.can_manage_member_permissions),
    can_manage_members: Boolean(context.can_manage_members),
    is_viewer: Boolean(context.is_viewer),
  }
  try {
    window.localStorage.setItem(AUTH_CONTEXT_KEY, JSON.stringify(normalized))
    if (normalized.email) window.localStorage.setItem('rezzerv_user_email', normalized.email)
    if (normalized.active_household_name) window.localStorage.setItem('rezzerv_household_name', normalized.active_household_name)
  } catch {}
  return normalized
}

export function markAuthCheckedForToken(token) {
  try {
    if (!token) {
      window.sessionStorage.removeItem(AUTH_CHECKED_TOKEN_KEY)
      return
    }
    window.sessionStorage.setItem(AUTH_CHECKED_TOKEN_KEY, token)
  } catch {}
}

export function isTokenAlreadyValidated(token) {
  if (!token) return false
  try {
    return window.sessionStorage.getItem(AUTH_CHECKED_TOKEN_KEY) === token
  } catch {
    return false
  }
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
  try {
    window.localStorage.removeItem('rezzerv_token')
    window.localStorage.removeItem('rezzerv_user_email')
    window.localStorage.removeItem('rezzerv_household_name')
    window.localStorage.removeItem(AUTH_CONTEXT_KEY)
  } catch {}
  try {
    window.sessionStorage.removeItem(AUTH_CHECKED_TOKEN_KEY)
  } catch {}
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

export async function fetchAuthContext() {
  const token = getStoredToken()
  if (!token) throw new Error('Geen actieve sessie')
  const response = await fetch('/api/auth/context', {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    cache: 'no-store',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = buildAuthErrorMessage(response.status, data?.detail || 'Je sessie is verlopen. Log opnieuw in.')
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  const stored = storeAuthContext(data)
  markAuthCheckedForToken(token)
  return stored
}

export async function fetchJsonWithAuth(url, options = {}) {
  const { headers: optionHeaders = {}, cache = 'no-store', ...restOptions } = options
  const mergedHeaders = {
    'Content-Type': 'application/json',
    ...optionHeaders,
  }
  const authHeaders = getAuthHeaders()
  if (!mergedHeaders.Authorization && authHeaders.Authorization) {
    mergedHeaders.Authorization = authHeaders.Authorization
  }

  const response = await fetch(url, {
    ...restOptions,
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
  return String(source?.display_role || '').trim().toLowerCase() === 'admin'
}

export function isHouseholdViewerFromContext(context = null) {
  const source = context || readStoredAuthContext()
  return String(source?.display_role || '').trim().toLowerCase() === 'viewer'
}

export function canCurrentUserPerform(permissionKey, context = null) {
  if (!permissionKey) return false
  const source = context || readStoredAuthContext()
  return Boolean(source?.permissions?.[permissionKey])
}
