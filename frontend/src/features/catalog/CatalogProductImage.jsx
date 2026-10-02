import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import '../../ui/catalogArticleThumbnail.css'

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
  const [zoomed, setZoomed] = useState(false)

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
    <>
      <div
        className={className}
        role="button"
        tabIndex={0}
        aria-label={normalizedText(productName) ? `Productfoto van ${normalizedText(productName)} vergroten` : 'Productfoto vergroten'}
        onClick={(event) => { event.stopPropagation(); setZoomed(true) }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            event.stopPropagation()
            setZoomed(true)
          }
        }}
      >
        <img
        src={src}
        alt={compact ? '' : `Productfoto van ${normalizedText(productName) || 'catalogusartikel'}`}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        />
      </div>
      {zoomed && typeof document !== 'undefined' ? createPortal(
        <button
          type="button"
          className="rz-product-image-overlay"
          onClick={(event) => { event.stopPropagation(); setZoomed(false) }}
          aria-label="Vergrote productfoto sluiten"
          data-testid="product-image-overlay"
        >
          <img src={src} alt={normalizedText(productName) ? `Productfoto van ${normalizedText(productName)}` : 'Productfoto'} referrerPolicy="no-referrer" />
        </button>,
        document.body,
      ) : null}
    </>
  )
}
