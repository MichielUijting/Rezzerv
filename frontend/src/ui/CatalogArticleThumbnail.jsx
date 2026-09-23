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
      <span
        className={classes}
        role="img"
        aria-label={normalizeText(productName) ? `Geen foto beschikbaar voor ${normalizeText(productName)}` : 'Geen foto beschikbaar'}
        data-testid="catalog-article-thumbnail-empty"
      >
        <span className="rz-catalog-article-thumbnail-empty-label">Geen foto</span>
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
