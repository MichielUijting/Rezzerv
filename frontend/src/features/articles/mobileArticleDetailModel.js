function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

export function isStableHouseholdArticleId(value) {
  const normalized = String(value || '').trim()
  return Boolean(normalized) && !normalized.startsWith('article::') && !normalized.startsWith('live::')
}

export function buildMobileArticleInventoryRows(liveRows = [], articleId = '', articleName = '') {
  const stableArticleId = isStableHouseholdArticleId(articleId) ? String(articleId).trim() : ''
  const articleNameKey = normalizeText(articleName)

  return (Array.isArray(liveRows) ? liveRows : [])
    .filter((row) => {
      const rowArticleId = String(row?.household_article_id || '').trim()
      if (stableArticleId) return rowArticleId === stableArticleId
      if (!articleNameKey) return false
      return normalizeText(row?.artikel || row?.household_article_name) === articleNameKey
    })
    .map((row) => ({
      id: String(row?.id || '').trim(),
      householdArticleId: String(row?.household_article_id || '').trim(),
      quantity: Number(row?.aantal ?? row?.quantity ?? 0) || 0,
      spaceId: String(row?.space_id || '').trim(),
      sublocationId: String(row?.sublocation_id || '').trim(),
      location: String(row?.locatie || row?.space_name || '').trim(),
      sublocation: String(row?.sublocatie || row?.sublocation_name || '').trim(),
    }))
    .filter((row) => Boolean(row.id))
}

export function chooseMobileInventoryRow(rows = [], settings = {}) {
  const candidates = Array.isArray(rows) ? rows : []
  if (!candidates.length) return null

  const defaultSublocationId = String(settings?.default_sublocation_id || '').trim()
  if (defaultSublocationId) {
    const match = candidates.find((row) => row.sublocationId === defaultSublocationId)
    if (match) return match
  }

  const defaultLocationId = String(settings?.default_location_id || '').trim()
  if (defaultLocationId) {
    const match = candidates.find((row) => row.spaceId === defaultLocationId)
    if (match) return match
  }

  return candidates[0]
}

export function formatMobileLocation(row) {
  if (!row) return 'Geen locatie'
  if (row.location && row.sublocation) return `${row.location} / ${row.sublocation}`
  return row.location || row.sublocation || 'Geen locatie'
}

function nullableNumber(value) {
  if (value === '' || value == null) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function buildHouseholdSettingsPayload(settings = {}, favoriteStore = '') {
  return {
    min_stock: nullableNumber(settings?.min_stock),
    ideal_stock: nullableNumber(settings?.ideal_stock),
    favorite_store: String(favoriteStore || '').trim(),
    average_price: nullableNumber(settings?.average_price),
    status: String(settings?.status || 'active').trim() || 'active',
    default_location_id: String(settings?.default_location_id || '').trim() || null,
    default_sublocation_id: String(settings?.default_sublocation_id || '').trim() || null,
    auto_restock: Boolean(settings?.auto_restock),
    packaging_unit: String(settings?.packaging_unit || '').trim(),
    packaging_quantity: nullableNumber(settings?.packaging_quantity),
    notes: String(settings?.notes || '').trim(),
  }
}

export function buildShoppingListPayload(articleData = {}, householdArticleId = '') {
  const articleName = String(articleData?.article_name || articleData?.name || '').trim()
  return {
    article_name: articleName,
    article_group_name: String(articleData?.article_group_name || articleData?.article_group || articleData?.category || '').trim(),
    product_type_name: String(articleData?.product_type_name || articleData?.article_type || articleData?.type || '').trim(),
    source_type: 'household_article',
    source_id: String(householdArticleId || articleData?.household_article_id || articleData?.article_id || articleData?.id || '').trim(),
  }
}

export function isMobileArticleAlmostOut(totalQuantity, minimumStock) {
  if (minimumStock === '' || minimumStock == null) return false
  const total = Number(totalQuantity)
  const minimum = Number(minimumStock)
  return Number.isFinite(total) && Number.isFinite(minimum) && total <= minimum
}

export function filterPurchaseHistory(history = []) {
  return (Array.isArray(history) ? history : []).filter((event) => {
    return String(event?.event_type || '').trim() === 'purchase'
      || String(event?.type || '').trim().toLowerCase() === 'aankoop'
  })
}
