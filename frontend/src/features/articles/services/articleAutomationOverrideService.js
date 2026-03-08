const STORAGE_KEY = 'rezzerv_article_auto_consume_overrides'

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

function writeAllOverrides(overrides) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides))
  window.dispatchEvent(new CustomEvent('rezzerv-article-auto-consume-overrides-updated', { detail: overrides }))
}

export function getArticleAutoConsumeMode(articleId) {
  const overrides = readAllOverrides()
  return normalizeMode(overrides[String(articleId)])
}

export function saveArticleAutoConsumeMode(articleId, mode) {
  const normalized = normalizeMode(mode)
  const overrides = readAllOverrides()
  overrides[String(articleId)] = normalized
  writeAllOverrides(overrides)
  return normalized
}
