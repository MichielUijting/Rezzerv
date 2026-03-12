import { API_BASE_URL } from '../../../lib/apiClient'

const ENDPOINT = `${API_BASE_URL}/api/settings/article-field-visibility`
const STORAGE_KEY = 'rezzerv_article_field_visibility'

export class ArticleFieldVisibilityServiceError extends Error {
  constructor(message, status = null, details = null) {
    super(message)
    this.name = 'ArticleFieldVisibilityServiceError'
    this.status = status
    this.details = details
  }
}

export function normalizeArticleFieldVisibility(data) {
  const base = { overview: {}, stock: {}, locations: {}, history: {}, analytics: {} }
  if (!data || typeof data !== 'object') return base
  for (const key of Object.keys(base)) {
    if (data[key] && typeof data[key] === 'object') base[key] = data[key]
  }
  return base
}

async function parseResponse(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    throw new ArticleFieldVisibilityServiceError('Ongeldige JSON ontvangen van de server.', response.status)
  }
}

function loadLocalFallback() {
  try {
    return normalizeArticleFieldVisibility(JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'))
  } catch {
    return normalizeArticleFieldVisibility({})
  }
}

function saveLocalFallback(map) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeArticleFieldVisibility(map)))
}

function getAuthHeaders() {
  const token = window.localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchArticleFieldVisibility() {
  try {
    const response = await fetch(ENDPOINT, {
      method: 'GET',
      headers: { Accept: 'application/json', ...getAuthHeaders() },
      credentials: 'include',
    })
    if (!response.ok) {
      const data = await parseResponse(response).catch(() => null)
      throw new ArticleFieldVisibilityServiceError(data?.detail || 'Voorkeuren konden niet worden geladen.', response.status, data)
    }
    const data = await parseResponse(response)
    const normalized = normalizeArticleFieldVisibility(data)
    saveLocalFallback(normalized)
    return { data: normalized, usedFallback: false, error: null }
  } catch (error) {
    const fallback = loadLocalFallback()
    return {
      data: fallback,
      usedFallback: true,
      error: error instanceof ArticleFieldVisibilityServiceError
        ? error
        : new ArticleFieldVisibilityServiceError('Voorkeuren konden niet worden geladen.', null, error),
    }
  }
}

export async function saveArticleFieldVisibility(visibilityMap) {
  const normalized = normalizeArticleFieldVisibility(visibilityMap)
  try {
    const response = await fetch(ENDPOINT, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...getAuthHeaders() },
      credentials: 'include',
      body: JSON.stringify(normalized),
    })
    if (!response.ok) {
      const data = await parseResponse(response).catch(() => null)
      throw new ArticleFieldVisibilityServiceError(data?.detail || 'Voorkeuren konden niet worden opgeslagen.', response.status, data)
    }
    const data = await parseResponse(response)
    const saved = normalizeArticleFieldVisibility(data)
    saveLocalFallback(saved)
    return { data: saved, usedFallback: false, error: null }
  } catch (error) {
    saveLocalFallback(normalized)
    return {
      data: normalized,
      usedFallback: true,
      error: error instanceof ArticleFieldVisibilityServiceError
        ? error
        : new ArticleFieldVisibilityServiceError('Voorkeuren konden niet worden opgeslagen.', null, error),
    }
  }
}
