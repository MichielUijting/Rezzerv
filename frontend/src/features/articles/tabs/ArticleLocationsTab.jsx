import { useMemo } from 'react'

function normalizeLocationName(value) {
  return value || 'Onbekende locatie'
}

function normalizeSubLocationName(value) {
  return value || 'Algemeen'
}

function formatQuantity(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return '0'
  return String(number)
}

function getPrimaryLocation(locations) {
  if (!locations.length) return null
  return [...locations].sort((a, b) => (Number(b?.aantal) || 0) - (Number(a?.aantal) || 0))[0]
}

export default function ArticleLocationsTab({ articleData = {} }) {
  const locations = Array.isArray(articleData.locations) ? articleData.locations : []

  const primaryLocation = useMemo(() => getPrimaryLocation(locations), [locations])

  const locationRows = useMemo(() => {
    return locations.map((entry, index) => ({
      key: `${entry?.locatie || 'locatie'}-${entry?.sublocatie || 'algemeen'}-${index}`,
      locatie: normalizeLocationName(entry?.locatie),
      sublocatie: normalizeSubLocationName(entry?.sublocatie),
      aantal: formatQuantity(entry?.aantal),
    }))
  }, [locations])

  if (!locationRows.length) {
    return <div className="rz-empty-state">Er zijn nog geen locatiegegevens bekend voor dit artikel.</div>
  }

  return (
    <div className="rz-locations-tab">
      <section className="rz-locations-summary-card rz-article-detail-section rz-article-detail-section--summary">
        <div className="rz-locations-summary-label">Primaire locatie</div>
        <div className="rz-locations-summary-value">{normalizeLocationName(primaryLocation?.locatie)}</div>
        <div className="rz-locations-summary-subvalue">{normalizeSubLocationName(primaryLocation?.sublocatie)}</div>
      </section>

      <section className="rz-locations-group rz-article-detail-section">
        <h3 className="rz-locations-group-title rz-article-detail-section-title">Alle locaties</h3>
        <div className="rz-locations-group-body rz-article-detail-section-body">
          {locationRows.map((row) => (
            <div key={row.key} className="rz-location-row">
              <div className="rz-location-row-main">
                <div className="rz-location-row-title">{row.locatie}</div>
                <div className="rz-location-row-subtitle">{row.sublocatie}</div>
              </div>
              <div className="rz-location-row-meta">
                <div className="rz-location-row-label">Aantal</div>
                <div className="rz-location-row-value">{row.aantal}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
