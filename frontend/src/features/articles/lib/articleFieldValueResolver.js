export const EMPTY_VALUE = '—'

function bool(value) {
  if (value === true) return 'Ja'
  if (value === false) return 'Nee'
  return EMPTY_VALUE
}

export function resolveArticleFieldValue(fieldKey, articleData = {}) {
  switch (fieldKey) {
    case 'article_name': return articleData.name || EMPTY_VALUE
    case 'custom_name': return articleData.custom_name || EMPTY_VALUE
    case 'article_type': return articleData.article_type || articleData.type || EMPTY_VALUE
    case 'category': return articleData.category || EMPTY_VALUE
    case 'brand_or_maker': return articleData.brand || articleData.maker || articleData.provider || EMPTY_VALUE
    case 'source': return articleData.source || 'demo'
    case 'status': return articleData.status || 'actief'
    case 'short_description': return articleData.short_description || articleData.description || EMPTY_VALUE
    case 'barcode': return articleData.barcode || EMPTY_VALUE
    case 'variant': return articleData.variant || EMPTY_VALUE
    case 'size_value': return articleData.size_value || articleData.weight || EMPTY_VALUE
    case 'size_unit': return articleData.size_unit || EMPTY_VALUE
    case 'purchase_date': return articleData.purchase_date || EMPTY_VALUE
    case 'calories': return articleData.calories ?? EMPTY_VALUE
    case 'fat_total': return articleData.fat_total ?? EMPTY_VALUE
    case 'emballage': return bool(articleData.emballage)
    case 'emballage_amount': return articleData.emballage_amount ?? EMPTY_VALUE
    case 'notes': return articleData.notes || EMPTY_VALUE
    default: return EMPTY_VALUE
  }
}
