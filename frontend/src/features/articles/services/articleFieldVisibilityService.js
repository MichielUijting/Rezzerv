const ENDPOINT = '/api/settings/article-field-visibility'
const STORAGE_KEY = 'rezzerv_article_field_visibility'

export class ArticleFieldVisibilityServiceError extends Error {
  constructor(message, status = null, details = null) {
    super(message)
    this.name = 'ArticleFieldVisibilityServiceError'
    this.status = status
    this.details = details
  }
}

function normalize(data) {
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
    return normalize(JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'))
  } catch {
    return normalize({})
  }
}

function saveLocalFallback(map) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalize(map)))
}

export async function fetchArticleFieldVisibility() {
  try {
    const response = await fetch(ENDPOINT, { method: 'GET', headers: { Accept: 'application/json' }, credentials: 'include' })
    if (!response.ok) throw new ArticleFieldVisibilityServiceError('Voorkeuren konden niet worden geladen.', response.status)
    const data = await parseResponse(response)
    const normalized = normalize(data)
    saveLocalFallback(normalized)
    return normalized
  } catch {
    return loadLocalFallback()
  }
}

export async function saveArticleFieldVisibility(visibilityMap) {
  const normalized = normalize(visibilityMap)
  try {
    const response = await fetch(ENDPOINT, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      credentials: 'include',
      body: JSON.stringify(normalized),
    })
    if (!response.ok) throw new ArticleFieldVisibilityServiceError('Voorkeuren konden niet worden opgeslagen.', response.status)
    const data = await parseResponse(response)
    const saved = normalize(data)
    saveLocalFallback(saved)
    return saved
  } catch {
    saveLocalFallback(normalized)
    return normalized
  }
}
