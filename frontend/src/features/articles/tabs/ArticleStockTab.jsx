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
    return locations.reduce((sum, entry) => sum + (Number(entry?.aantal ?? entry?.quantity) || 0), 0)
  }, [locations])

  const inventoryRows = useMemo(() => {
    return locations.map((entry, index) => ({
      rowKey: `${entry?.locatie || 'locatie'}-${entry?.sublocatie || 'algemeen'}-${index}`,
      locationName: normalizeLocationName(entry?.locatie ?? entry?.space_name),
      sublocationName: normalizeSubLocationName(entry?.sublocatie ?? entry?.sublocation_name),
      quantity: Number(entry?.aantal ?? entry?.quantity) || 0,
    }))
  }, [locations])

  return (
    <div className="rz-stock-tab">
      <section className="rz-stock-summary-card rz-article-detail-section rz-article-detail-section--summary">
        <div className="rz-stock-summary-label">Totale voorraad</div>
        <div className="rz-stock-summary-value">{totalQuantity}</div>
      </section>

      {inventoryRows.length === 0 ? (
        <div className="rz-empty-state">Er zijn nog geen voorraadlocaties bekend voor dit artikel.</div>
      ) : (
        <section className="rz-stock-block rz-article-detail-section">
          <h3 className="rz-stock-block-title rz-article-detail-section-title">Voorraad per sublocatie</h3>
          <div className="rz-stock-block-body rz-article-detail-section-body">
            <div className="rz-stock-summary-table" role="table" aria-label="Voorraad per sublocatie">
              <div className="rz-stock-summary-table-header" role="row">
                <div role="columnheader">Locatie</div>
                <div role="columnheader">Sublocatie</div>
                <div role="columnheader" className="rz-stock-summary-table-header-quantity">Aantal</div>
              </div>
              {inventoryRows.map((row) => (
                <div key={row.rowKey} className="rz-stock-summary-table-row" role="row" data-testid={`article-stock-row-${row.rowKey}`}>
                  <span>{row.locationName}</span>
                  <span>{row.sublocationName}</span>
                  <span className="rz-stock-summary-table-quantity">{formatQuantity(row.quantity)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
