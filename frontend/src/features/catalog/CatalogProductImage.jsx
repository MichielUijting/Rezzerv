import { useEffect, useState } from 'react'

function normalizedText(value) {
  return String(value ?? '').trim()
}

export default function CatalogProductImage({
  imageUrl,
  productName,
  compact = false,
}) {
  const src = normalizedText(imageUrl)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  const className = compact
    ? 'rz-catalog-product-image rz-catalog-product-image--compact'
    : 'rz-catalog-product-image'

  if (!src || failed) {
    return (
      <div className={className} data-testid="catalog-product-image-fallback">
        <span className="rz-catalog-product-image-fallback">Geen foto</span>
      </div>
    )
  }

  return (
    <div className={className}>
      <img
        src={src}
        alt={compact ? '' : `Productfoto van ${normalizedText(productName) || 'catalogusartikel'}`}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </div>
  )
}
