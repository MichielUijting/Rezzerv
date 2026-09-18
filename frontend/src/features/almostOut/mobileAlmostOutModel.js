function normalizeNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export function formatAlmostOutQuantity(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)))
}

function buildPackagingLabel(item) {
  const unit = String(item?.packaging_unit || item?.verpakkingseenheid || '').trim()
  const quantity = item?.packaging_quantity ?? item?.verpakkingshoeveelheid
  const normalizedQuantity = Number(quantity)
  if (unit && Number.isFinite(normalizedQuantity) && normalizedQuantity > 0) {
    return `${formatAlmostOutQuantity(normalizedQuantity)} ${unit}`
  }
  if (unit) return unit
  if (Number.isFinite(normalizedQuantity) && normalizedQuantity > 0) return formatAlmostOutQuantity(normalizedQuantity)
  return '—'
}

function buildLocationLabel(item) {
  const primary = item?.primary_location && typeof item.primary_location === 'object' ? item.primary_location : null
  const fallback = item?.default_location && typeof item.default_location === 'object' ? item.default_location : null
  const source = primary || fallback
  if (!source) return '—'
  const spaceName = String(source.space_name || source.locatie || '').trim()
  const sublocationName = String(source.sublocation_name || source.sublocatie || '').trim()
  if (spaceName && sublocationName) return `${spaceName} / ${sublocationName}`
  if (spaceName) return spaceName
  if (sublocationName) return sublocationName
  return '—'
}

export function normalizeAlmostOutText(value) {
  return String(value || '').trim().toLowerCase()
}

export function buildMobileAlmostOutRows(items = []) {
  return (items || []).map((item, index) => {
    const householdName = String(item?.household_article_name || '').trim()
    const productName = String(item?.product_name || item?.article_name || '').trim()
    const primaryName = householdName || productName || 'Onbekend artikel'
    const householdArticleId = String(item?.household_article_id || item?.article_id || '').trim()

    return {
      id: householdArticleId || String(item?.article_name || `almost-out-${index}`),
      detailId: householdArticleId,
      primaryName,
      householdName,
      productName,
      currentQuantity: normalizeNumber(item?.current_quantity ?? item?.huidige_voorraad),
      minStock: normalizeNumber(item?.min_stock ?? item?.minimumvoorraad),
      idealStock: normalizeNumber(item?.ideal_stock ?? item?.streefvoorraad),
      amountToBuy: normalizeNumber(item?.amount_to_buy ?? item?.aantal_te_kopen),
      packaging: buildPackagingLabel(item),
      location: buildLocationLabel(item),
    }
  })
}
