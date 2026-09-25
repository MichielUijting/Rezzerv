import CatalogArticleThumbnail from './CatalogArticleThumbnail.jsx'

export default function MobileArticleRow({
  title,
  subtitle = '',
  meta = [],
  imageUrl = '',
  imageProductName = '',
  leading = null,
  side = null,
  onActivate = null,
  testId = undefined,
  checked = false,
}) {
  const interactive = typeof onActivate === 'function'
  return (
    <div
      className={`rz-mobile-inventory-card${interactive ? '' : ' rz-mobile-article-row--static'}${checked ? ' rz-mobile-article-row--checked' : ''}`}
      role={interactive ? 'link' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onActivate : undefined}
      onKeyDown={interactive ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onActivate()
        }
      } : undefined}
      data-testid={testId}
    >
      {leading ? <div className="rz-mobile-article-row-leading">{leading}</div> : null}
      <CatalogArticleThumbnail
        imageUrl={imageUrl}
        productName={imageProductName || title}
        className="rz-mobile-inventory-product-thumbnail"
      />
      <div className="rz-mobile-inventory-card-main">
        <div className="rz-mobile-inventory-card-title">{title}</div>
        {subtitle ? <div className="rz-mobile-inventory-card-product">{subtitle}</div> : null}
        {meta.filter(Boolean).length > 0 ? (
          <div className="rz-mobile-inventory-card-meta">
            {meta.filter(Boolean).map((value, index) => <span key={`${value}-${index}`}>{value}</span>)}
          </div>
        ) : null}
      </div>
      {side ? <div className="rz-mobile-inventory-card-side">{side}</div> : null}
    </div>
  )
}
