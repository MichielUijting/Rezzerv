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

export default function ArticleStockTab({ article = {}, articleData }) {
  const sourceArticle = articleData ?? article

  const locations = Array.isArray(sourceArticle.locations) ? sourceArticle.locations : []

  const totalQuantity = useMemo(() => {
    return locations.reduce((sum, entry) => sum + (Number(entry?.aantal) || 0), 0)
  }, [locations])

  const groupedLocations = useMemo(() => {
    return locations.reduce((acc, entry) => {
      const locationName = normalizeLocationName(entry?.locatie)
      if (!acc[locationName]) {
        acc[locationName] = []
      }
      acc[locationName].push({
        sublocatie: normalizeSubLocationName(entry?.sublocatie),
        aantal: Number(entry?.aantal) || 0,
      })
      return acc
    }, {})
  }, [locations])

  return (
    <div className="rz-stock-tab">
      <section className="rz-stock-summary-card">
        <div className="rz-stock-summary-label">Totale voorraad</div>
        <div className="rz-stock-summary-value">{totalQuantity}</div>
      </section>

      {Object.keys(groupedLocations).length === 0 ? (
        <div className="rz-empty-state">Er zijn nog geen voorraadlocaties bekend voor dit artikel.</div>
      ) : (
        <div className="rz-stock-blocks">
          {Object.entries(groupedLocations).map(([locationName, entries]) => (
            <section key={locationName} className="rz-stock-block">
              <h3 className="rz-stock-block-title">{locationName}</h3>
              <div className="rz-stock-block-body">
                {entries.map((entry, index) => (
                  <div key={`${locationName}-${entry.sublocatie}-${index}`} className="rz-stock-row">
                    <div className="rz-stock-row-location">{entry.sublocatie}</div>
                    <div className="rz-stock-row-quantity">{formatQuantity(entry.aantal)}</div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
