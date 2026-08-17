import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth } from '../../../lib/authSession'

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
    const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household-articles/${encodeURIComponent(articleId)}/automation-override`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data?.detail || 'Override kon niet worden geladen.')
    }
    const explicit = Boolean(data?.has_explicit_override ?? data?.hasExplicitOverride)
    if (!explicit) {
      const legacyMode = readLegacyOverride(articleId)
      // follow_household is the server default, not a meaningful legacy override.
      // Never turn a read/cache of the default into a backend write.
      if (
        legacyMode !== null
        && legacyMode !== AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD
      ) {
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
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household-articles/${encodeURIComponent(articleId)}/automation-override`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
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
