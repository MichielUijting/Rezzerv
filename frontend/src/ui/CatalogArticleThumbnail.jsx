import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import './catalogArticleThumbnail.css'

function normalizeText(value) {
  return String(value ?? '').trim()
}

export default function CatalogArticleThumbnail({
  imageUrl,
  productName,
  className = '',
}) {
  const src = normalizeText(imageUrl)
  const [failed, setFailed] = useState(false)
  const [zoomed, setZoomed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  const classes = [
    'rz-catalog-article-thumbnail',
    (!src || failed) ? 'rz-catalog-article-thumbnail--empty' : '',
    className,
  ].filter(Boolean).join(' ')

  if (!src || failed) {
    return (
      <span
        className={classes}
        role="img"
        aria-label="Geen foto"
        data-testid="catalog-article-thumbnail-empty"
      >
        <span className="rz-catalog-article-thumbnail-empty-label">Geen foto</span>
      </span>
    )
  }

  return (
    <>
      <span
        className={classes}
        data-testid="catalog-article-thumbnail"
        role="button"
        tabIndex={0}
        aria-label={normalizeText(productName) ? `Productfoto van ${normalizeText(productName)} vergroten` : 'Productfoto vergroten'}
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
        alt=""
        title={normalizeText(productName) ? `Productfoto van ${normalizeText(productName)}` : 'Productfoto'}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        />
      </span>
      {zoomed && typeof document !== 'undefined' ? createPortal(
        <button
          type="button"
          className="rz-product-image-overlay"
          onClick={(event) => { event.stopPropagation(); setZoomed(false) }}
          aria-label="Vergrote productfoto sluiten"
          data-testid="product-image-overlay"
        >
          <img src={src} alt={normalizeText(productName) ? `Productfoto van ${normalizeText(productName)}` : 'Productfoto'} referrerPolicy="no-referrer" />
        </button>,
        document.body,
      ) : null}
    </>
  )
}
