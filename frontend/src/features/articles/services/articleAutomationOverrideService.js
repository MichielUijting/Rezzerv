import { API_BASE_URL } from '../../../lib/apiClient'

const STORAGE_KEY = 'rezzerv_article_auto_consume_overrides'
const EVENT_NAME = 'rezzerv-article-auto-consume-overrides-updated'

export const AUTO_CONSUME_MODES = {
  FOLLOW_HOUSEHOLD: 'follow_household',
  ALWAYS_ON: 'always_on',
  ALWAYS_OFF: 'always_off',
}

function normalizeMode(value) {
  if (value === AUTO_CONSUME_MODES.ALWAYS_ON) return AUTO_CONSUME_MODES.ALWAYS_ON
  if (value === AUTO_CONSUME_MODES.ALWAYS_OFF) return AUTO_CONSUME_MODES.ALWAYS_OFF
  return AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD
}

function getAuthHeaders() {
  const token = window.localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function readAllOverrides() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function readLegacyOverride(articleId) {
  const overrides = readAllOverrides()
  if (!Object.prototype.hasOwnProperty.call(overrides, String(articleId))) {
    return null
  }
  return normalizeMode(overrides[String(articleId)])
}

function writeAllOverrides(overrides) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides))
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: overrides }))
}

export function getArticleAutoConsumeMode(articleId) {
  const overrides = readAllOverrides()
  return normalizeMode(overrides[String(articleId)])
}

export async function fetchArticleAutoConsumeMode(articleId) {
  if (!articleId) return AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD
  try {
    const response = await fetch(`${API_BASE_URL}/api/household-articles/${encodeURIComponent(articleId)}/automation-override`, {
      method: 'GET',
      headers: { Accept: 'application/json', ...getAuthHeaders() },
      credentials: 'include',
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data?.detail || 'Override kon niet worden geladen.')
    }
    const explicit = Boolean(data?.has_explicit_override ?? data?.hasExplicitOverride)
    if (!explicit) {
      const legacyMode = readLegacyOverride(articleId)
      if (legacyMode !== null) {
        return saveArticleAutoConsumeMode(articleId, legacyMode)
      }
    }
    const overrides = readAllOverrides()
    overrides[String(data?.article_id || articleId)] = normalizeMode(data?.mode)
    writeAllOverrides(overrides)
    return normalizeMode(data?.mode)
  } catch {
    return getArticleAutoConsumeMode(articleId)
  }
}

export async function saveArticleAutoConsumeMode(articleId, mode) {
  const normalized = normalizeMode(mode)
  const response = await fetch(`${API_BASE_URL}/api/household-articles/${encodeURIComponent(articleId)}/automation-override`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...getAuthHeaders(),
    },
    credentials: 'include',
    body: JSON.stringify({ mode: normalized }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Override kon niet worden opgeslagen.')
  }
  const overrides = readAllOverrides()
  overrides[String(data?.article_id || articleId)] = normalizeMode(data?.mode)
  writeAllOverrides(overrides)
  return normalizeMode(data?.mode)
}
