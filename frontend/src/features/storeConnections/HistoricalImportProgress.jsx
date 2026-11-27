import { useState } from 'react'
import Button from '../../ui/Button'
import { fetchJson } from '../stores/storeImportShared.jsx'
import {
  historyCount, historicalStoreRows,
} from './historicalImportStatusModel.js'

/**
 * Durable, household-scoped progress: no provider total and no made-up percent.
 * A browser transfer only counts as imported after the canonical Kassa record.
 */
export default function HistoricalImportProgress({ summary, loading, error, onRefresh }) {
  const rows = historicalStoreRows(summary)
  const [evidence, setEvidence] = useState({ provider: '', loading: false, items: [], error: '' })
  const [recalculation, setRecalculation] = useState({ busy: false, message: '', error: '' })
  async function recalculateHistoricalStock() {
    setRecalculation({ busy: true, message: '', error: '' })
    try {
      const result = await fetchJson('/api/receipts/retailers/history-recalculate', { method: 'POST' })
      if (result?.queued !== true || result?.completed !== false) {
        throw new Error('Geen bevestigde opdracht voor de historische controle ontvangen.')
      }
      setRecalculation({ busy: false,
        message: 'Controle aangevraagd. Bestaande bonnen blijven bewaard. Dit is nog geen bevestiging dat de voorraad is herberekend.',
        error: '' })
      onRefresh?.()
    } catch {
      setRecalculation({ busy: false, message: '',
        error: 'Historische controle kon niet worden aangevraagd. Er is geen voorraad gewijzigd door dit verzoek.' })
    }
  }
  async function showEvidence(provider) {
    if (evidence.provider === provider && !evidence.loading) {
      setEvidence({ provider: '', loading: false, items: [], error: '' })
      return
    }
    setEvidence({ provider, loading: true, items: [], error: '' })
    try {
      const data = await fetchJson('/api/receipts/retailers/history-evidence?provider=' + encodeURIComponent(provider))
      setEvidence({ provider, loading: false, items: Array.isArray(data?.items) ? data.items : [], error: '' })
    } catch {
      setEvidence({ provider, loading: false, items: [], error: 'De brongegevens konden niet worden opgehaald. Probeer opnieuw.' })
    }
  }
  const receiptLabel = (value) => historyCount(value) + (value === 1 ? ' bon' : ' bonnen')
  return (
    <section data-testid="historical-import-progress" aria-labelledby="historical-import-title"
      style={{ display: 'grid', rowGap: '12px', minWidth: 0 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <h3 id="historical-import-title" style={{ margin: 0 }}>Historische aankopen</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {summary?.history_cutover_enabled ? (
            <Button type="button" variant="secondary" onClick={() => { void recalculateHistoricalStock() }}
              disabled={recalculation.busy} data-testid="historical-stock-recalculate">
              {recalculation.busy ? 'Aanvragen…' : 'Bestaande bonnen opnieuw controleren'}
            </Button>
          ) : null}
          <Button type="button" variant="secondary" onClick={onRefresh}
            disabled={loading} data-testid="historical-import-refresh">
            {loading ? 'Bijwerken…' : 'Vernieuwen'}
          </Button>
        </div>
      </div>
      <p style={{ margin: 0 }}>
        Dit zijn bonnen die Inhuis als opgeslagen registreert, ook als ze niet zichtbaar zijn
        in de gewone Kassa-lijst. De winkel bepaalt hoeveel oudere bonnen beschikbaar zijn;
        daarom tonen we geen onbevestigd totaal of percentage.
        Bonnen uit de wachtrij zijn nog niet verwerkt in Kassa. Ook gekoppelde
        artikelregels zijn niet automatisch als voorraad geboekt. Via 'Welke bonnen?'
        controleer je welke opgeslagen records meetellen.
      </p>
      {summary && summary.history_cutover_enabled === false ? (
        <p data-testid="historical-import-no-cutover" style={{ margin: 0 }}>
          Voor dit bestaande huishouden is geen historische startgrens vastgelegd.
          Ingelezen bonnen zijn zichtbaar, maar er wordt geen aantal historische aankopen gegokt.
        </p>
      ) : null}
      {summary?.historical_stock ? (
        <div data-testid="historical-stock-outcome" style={{ display: 'grid', rowGap: '4px' }}>
          <span>Historische inleesperiode vanaf: {summary.history_start_date || 'onbekend'} (tot de start van het huishouden).</span>
          <span>Daadwerkelijk vastgelegde historische beginvoorraad: {historyCount(summary.historical_stock.baseline_article_count)} artikelen, {historyCount(summary.historical_stock.baseline_unit_count)} stuks.</span>
          <span>Artikelen met bewezen herhaalaankooptermijn: {historyCount(summary.historical_stock.repurchase_cadence_article_count)}.</span>
        </div>
      ) : null}
      {summary?.auto_import_paused ? (
        <p data-testid="historical-import-paused" style={{ margin: 0 }}>
          De automatische winkelimport is momenteel gepauzeerd. Al ontvangen
          bonnen blijven bewaard; dit overzicht hervat de verwerking niet.
        </p>
      ) : null}
      {recalculation.message ? <p role="status" data-testid="historical-stock-recalculate-queued" style={{ margin: 0 }}>
        {recalculation.message}
      </p> : null}
      {recalculation.error ? <p role="alert" data-testid="historical-stock-recalculate-error" style={{ margin: 0 }}>
        {recalculation.error}
      </p> : null}
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
              <span>Opgeslagen bonnen (niet noodzakelijk in Kassa): {receiptLabel(row.kassa_receipts)}</span>
              <span>Waarvan nog in Kassa te behandelen: {receiptLabel(row.kassa_inbox_receipts)}</span>
              <span>Historische bonnen bruikbaar voor analyse: {historyCount(row.historical_receipts)}</span>
              <span>Historische bonregels: {historyCount(row.historical_line_count)}
                {' · '}Fysieke artikelkandidaten: {historyCount(row.physical_candidate_line_count)}</span>
              <span>Rechtstreeks gekoppelde artikelregels: {historyCount(row.directly_linked_line_count)}
                {' · '}Fysieke artikelregels zonder huishoudartikelkoppeling: {historyCount(row.unlinked_physical_line_count)}</span>
              <span>Onzeker geclassificeerde bonregels: {historyCount(row.uncertain_line_count)}.
                Dit zijn controlecategorieën; alleen bewezen regels kunnen worden gebruikt bij voorraadopbouw.</span>
              <span>Ontvangen, nog in wachtrij: {historyCount(row.queue_pending)}
                {' · '}Bezig met verwerken: {historyCount(row.queue_processing)}</span>
              <span>Controle nodig: {historyCount(row.queue_review_required)}
                {' · '}Opgeslagen bonnen met onzekere datum of verwerking: {historyCount(row.review_receipts)}</span>
              <div>
                <Button type="button" variant="secondary"
                  data-testid={'historical-import-evidence-' + row.code}
                  aria-expanded={evidence.provider === row.code}
                  disabled={evidence.loading && evidence.provider === row.code}
                  onClick={() => { void showEvidence(row.code) }}>
                  {evidence.provider === row.code && evidence.loading ? 'Bron controleren…' : 'Welke bonnen?'}
                </Button>
              </div>
              {evidence.provider === row.code && !evidence.loading ? (
                <div data-testid={'historical-import-evidence-panel-' + row.code}
                  style={{ display: 'grid', rowGap: '8px', minWidth: 0 }}>
                  <strong>Opgeslagen bongegevens van {row.name}</strong>
                  <p style={{ margin: 0 }}>De nieuwste bewaarde bonrecords, niet noodzakelijk
                    alle bonnen van de winkel.</p>
                  {evidence.error ? <p role="status">{evidence.error}</p> : null}
                  {!evidence.error && evidence.items.length === 0 ? (
                    <p style={{ margin: 0 }}>Geen verwerkt bonrecord gevonden.
                      Er kan wel een ontvangen bronrecord bestaan.</p>
                  ) : null}
                  {!evidence.error ? (
                    <ol style={{ margin: 0, paddingLeft: '24px' }}>
                      {evidence.items.map((item, index) => (
                        <li key={index}>
                          Aankoopdatum: {item.purchase_date || 'onbekend'};
                          ontvangen: {item.received_date || 'onbekend'};
                          artikelregels: {historyCount(item.line_count)};
                          verwerking: {item.approved ? 'goedgekeurd' : item.parse_status || 'onbekend'}.
                          {item.purchase_date_source === 'import_default'
                            ? ' Aankoopdatum is niet bevestigd.' : ''}
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
