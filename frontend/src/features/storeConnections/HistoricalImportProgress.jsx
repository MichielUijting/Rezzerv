import Button from '../../ui/Button'
import {
  historyCount, historicalStoreRows,
} from './historicalImportStatusModel.js'

/**
 * Durable, household-scoped progress: no provider total and no made-up percent.
 * A browser transfer only counts as imported after the canonical Kassa record.
 */
export default function HistoricalImportProgress({ summary, loading, error, onRefresh }) {
  const rows = historicalStoreRows(summary)
  return (
    <section data-testid="historical-import-progress" aria-labelledby="historical-import-title"
      style={{ display: 'grid', rowGap: '12px', minWidth: 0 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <h3 id="historical-import-title" style={{ margin: 0 }}>Historische aankopen</h3>
        <Button type="button" variant="secondary" onClick={onRefresh}
          disabled={loading} data-testid="historical-import-refresh">
          {loading ? 'Bijwerken…' : 'Vernieuwen'}
        </Button>
      </div>
      <p style={{ margin: 0 }}>
        Dit zijn de bonnen die Inhuis echt heeft opgeslagen. De winkel bepaalt hoeveel
        oudere bonnen beschikbaar zijn; daarom tonen we geen onbevestigd totaal of percentage.
        Bonnen uit de wachtrij zijn nog niet verwerkt in Kassa.
      </p>
      {summary && summary.history_cutover_enabled === false ? (
        <p data-testid="historical-import-no-cutover" style={{ margin: 0 }}>
          Voor dit bestaande huishouden is geen historische startgrens vastgelegd.
          Ingelezen bonnen zijn zichtbaar, maar er wordt geen aantal historische aankopen gegokt.
        </p>
      ) : null}
      {summary?.auto_import_paused ? (
        <p data-testid="historical-import-paused" style={{ margin: 0 }}>
          De automatische winkelimport is momenteel gepauzeerd. Al ontvangen
          bonnen blijven bewaard; dit overzicht hervat de verwerking niet.
        </p>
      ) : null}
      {error ? <p role="status" data-testid="historical-import-error" style={{ margin: 0 }}>
        {error}
      </p> : null}
      {!summary ? (
        <p style={{ margin: 0 }} data-testid="historical-import-not-loaded">
          {loading ? 'Importstatus ophalen…' : 'Importstatus nog niet beschikbaar.'}
        </p>
      ) : (
        <div role="list" data-testid="historical-import-stores"
          style={{ display: 'grid', rowGap: '12px', minWidth: 0 }}>
          {rows.map(row => (
            <div role="listitem" key={row.code} data-testid={'historical-import-' + row.code}
              style={{ display: 'grid', rowGap: '4px', paddingBottom: '12px', borderBottom: '1px solid var(--color-border, #d9dfe3)' }}>
              <strong>{row.name}</strong>
              <span>In Kassa: {historyCount(row.kassa_receipts)} bonnen</span>
              <span>Historische bonnen bruikbaar voor analyse: {historyCount(row.historical_receipts)}</span>
              <span>Ontvangen, nog in wachtrij: {historyCount(row.queue_pending)}
                {' · '}Bezig met verwerken: {historyCount(row.queue_processing)}</span>
              <span>Controle nodig: {historyCount(row.queue_review_required)}
                {' · '}Opgeslagen bonnen met onzekere datum of verwerking: {historyCount(row.review_receipts)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
