import { ArticleSectionAccordion } from './ArticleSectionControls'

function hasValue(value) {
  if (value == null) return false
  if (Array.isArray(value)) return value.length > 0
  return String(value).trim() !== ''
}

function SummaryRow({ label, value }) {
  if (!hasValue(value)) return null
  return (
    <div className="rz-field-row">
      <div className="rz-field-row-label">{label}:</div>
      <div className="rz-field-row-value">{value}</div>
    </div>
  )
}

function humanizeSourceName(sourceName) {
  const key = String(sourceName || '').trim().toLowerCase()
  if (!key) return ''
  if (key === 'internal_catalog') return 'Interne productcatalogus'
  if (key === 'openfoodfacts' || key === 'open_food_facts') return 'Open Food Facts'
  if (key === 'public_reference' || key === 'public_reference_catalog') return 'Public reference catalog'
  if (key === 'gs1' || key === 'gs1_my_product_manager_share') return 'GS1 My Product Manager Share'
  return sourceName
}

export function ArticleIdentitySummary({ articleData = {} }) {
  const identity = articleData?.product_details?.identity || {}
  const barcode = articleData?.barcode || identity?.normalized_barcode || identity?.identity_value || ''
  const articleNumber = articleData?.article_number || ''
  const source = humanizeSourceName(articleData?.source || identity?.source)

  return (
    <ArticleSectionAccordion
      title="Productidentiteit"
      testId="article-identity-summary"
      sectionClassName="rz-overview-group rz-article-detail-section"
      titleClassName="rz-overview-group-title rz-article-detail-section-title"
      contentClassName="rz-overview-group-body rz-article-detail-section-body"
    >
      <SummaryRow label="Barcode" value={barcode} />
      <SummaryRow label="Extern artikelnummer" value={articleNumber} />
      <SummaryRow label="Bron" value={source} />
      {!hasValue(barcode) && !hasValue(articleNumber) && !hasValue(source) ? (
        <div className="rz-empty-state">Nog geen productidentiteit gekoppeld.</div>
      ) : null}
    </ArticleSectionAccordion>
  )
}

export function ArticleProductSummary({ articleData = {} }) {
  const enrichment = articleData?.product_details?.enrichment || {}
  const productName = enrichment?.title || articleData?.article_name || articleData?.name || ''
  const brand = enrichment?.brand || articleData?.brand_or_maker || articleData?.brand || ''
  const category = enrichment?.category || articleData?.category || ''
  const sizeValue = enrichment?.size_value ?? articleData?.size_value
  const sizeUnit = enrichment?.size_unit || articleData?.size_unit || ''
  const size = sizeValue != null && String(sizeValue).trim() !== ''
    ? `${sizeValue}${sizeUnit ? ` ${sizeUnit}` : ''}`
    : ''
  const ingredients = Array.isArray(enrichment?.ingredients) ? enrichment.ingredients.filter(Boolean).join(', ') : ''
  const allergens = Array.isArray(enrichment?.allergens) ? enrichment.allergens.filter(Boolean).join(', ') : ''
  const source = humanizeSourceName(enrichment?.source_name)

  const hasProductData = [productName, brand, category, size, ingredients, allergens, source].some(hasValue)

  return (
    <ArticleSectionAccordion
      title="Productinformatie"
      testId="article-product-summary"
      sectionClassName="rz-overview-group rz-article-detail-section"
      titleClassName="rz-overview-group-title rz-article-detail-section-title"
      contentClassName="rz-overview-group-body rz-article-detail-section-body"
    >
      {hasProductData ? (
        <>
          <SummaryRow label="Productnaam" value={productName} />
          <SummaryRow label="Merk" value={brand} />
          <SummaryRow label="Categorie" value={category} />
          <SummaryRow label="Inhoud" value={size} />
          <SummaryRow label="Ingrediënten" value={ingredients} />
          <SummaryRow label="Allergenen" value={allergens} />
          <SummaryRow label="Bron" value={source} />
        </>
      ) : (
        <div className="rz-empty-state">Nog geen aanvullende productinformatie beschikbaar.</div>
      )}
    </ArticleSectionAccordion>
  )
}
