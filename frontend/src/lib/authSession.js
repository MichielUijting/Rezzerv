const AUTH_CONTEXT_KEY = 'rezzerv_auth_context'
const AUTH_CHECKED_TOKEN_KEY = 'rezzerv_auth_checked_token'
const LOGIN_MESSAGE_KEY = 'rezzerv_login_message'
const TOKEN_KEY = 'rezzerv_token'
const USER_EMAIL_KEY = 'rezzerv_user_email'
const HOUSEHOLD_NAME_KEY = 'rezzerv_household_name'
const SESSION_KEYS = [TOKEN_KEY, USER_EMAIL_KEY, HOUSEHOLD_NAME_KEY, AUTH_CONTEXT_KEY]

function safeWindow() {
  return typeof window !== 'undefined' ? window : null
}

function explicitDevTokenEmail(token) {
  const prefix = 'rezzerv-dev-token::'
  const normalized = String(token || '').trim()
  if (!normalized.startsWith(prefix)) return ''
  return normalized.slice(prefix.length).trim().toLowerCase()
}

function migrateLegacySessionValue(key) {
  const win = safeWindow()
  if (!win) return ''
  try {
    const current = win.sessionStorage.getItem(key)
    if (current !== null) return current
    const legacy = win.localStorage.getItem(key)
    if (legacy === null) return ''
    win.sessionStorage.setItem(key, legacy)
    win.localStorage.removeItem(key)
    return legacy
  } catch {
    return ''
  }
}

function removeLegacySessionValues() {
  const win = safeWindow()
  if (!win) return
  try {
    for (const key of SESSION_KEYS) win.localStorage.removeItem(key)
  } catch {}
}

export function getStoredToken() {
  return migrateLegacySessionValue(TOKEN_KEY)
}

export function getAuthHeaders() {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function readStoredAuthContext() {
  try {
    const raw = migrateLegacySessionValue(AUTH_CONTEXT_KEY)
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
    window.sessionStorage.setItem(AUTH_CONTEXT_KEY, JSON.stringify(normalized))
    if (normalized.email) window.sessionStorage.setItem(USER_EMAIL_KEY, normalized.email)
    if (normalized.active_household_name) window.sessionStorage.setItem(HOUSEHOLD_NAME_KEY, normalized.active_household_name)
    removeLegacySessionValues()
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
    for (const key of SESSION_KEYS) window.sessionStorage.removeItem(key)
    window.sessionStorage.removeItem(AUTH_CHECKED_TOKEN_KEY)
  } catch {}
  removeLegacySessionValues()
  setLoginMessage(message)
}

export function beginNewAuthSession(token, email = '') {
  clearAuthSession('')
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token)
    if (email) window.sessionStorage.setItem(USER_EMAIL_KEY, email)
  } catch {}
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
  const requestToken = getStoredToken()
  if (!requestToken) throw new Error('Geen actieve sessie')
  const response = await fetch('/api/auth/context', {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${requestToken}`,
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

  if (getStoredToken() !== requestToken) {
    const error = new Error('Een nieuwere sessie is actief; verouderde autorisatiecontext is genegeerd.')
    error.code = 'STALE_AUTH_SESSION'
    throw error
  }

  const expectedEmail = explicitDevTokenEmail(requestToken)
  const contextEmail = String(data?.email || data?.user_id || '').trim().toLowerCase()
  if (expectedEmail && contextEmail !== expectedEmail) {
    const error = new Error('De autorisatiecontext hoort niet bij de actieve gebruiker. Log opnieuw in.')
    error.code = 'AUTH_CONTEXT_MISMATCH'
    throw error
  }

  const stored = storeAuthContext(data)
  markAuthCheckedForToken(requestToken)
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
