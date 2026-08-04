export function normalizeHouseholdArticleOption(article) {
  const householdArticleId = String(
    article?.household_article_id
      || article?.householdArticleId
      || article?.article_id
      || article?.id
      || '',
  ).trim()
  const name = String(
    article?.name
      || article?.article_name
      || article?.household_article_name
      || article?.naam
      || article?.label
      || '',
  ).trim()
  return {
    ...article,
    id: householdArticleId,
    household_article_id: householdArticleId,
    name,
    brand: String(article?.brand || article?.brand_or_maker || '').trim(),
  }
}

export function normalizeHouseholdArticleOptionsPayload(payload) {
  const sourceItems = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : []
  const byId = new Map()
  sourceItems.forEach((item) => {
    const normalized = normalizeHouseholdArticleOption(item)
    if (!normalized.id) return
    byId.set(normalized.id, normalized)
  })
  const items = [...byId.values()]
  return Array.isArray(payload) ? items : { ...payload, items }
}

export function shouldNormalizeHouseholdArticleOptions(url, method = 'GET') {
  return String(method || 'GET').toUpperCase() === 'GET'
    && /^\/api\/store-review-articles(?:\?|$)/.test(String(url || ''))
}
