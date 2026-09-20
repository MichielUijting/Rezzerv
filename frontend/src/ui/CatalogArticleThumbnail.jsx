import { useEffect, useState } from 'react'
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
      <span className={classes} aria-hidden="true" data-testid="catalog-article-thumbnail-empty">
        <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
          <rect x="3.5" y="5" width="17" height="14" rx="2" />
          <circle cx="9" cy="10" r="1.5" />
          <path d="m5.5 17 4.2-4 3.1 2.8 2.3-2.2 3.4 3.4" />
        </svg>
      </span>
    )
  }

  return (
    <span className={classes} data-testid="catalog-article-thumbnail">
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
  )
}
