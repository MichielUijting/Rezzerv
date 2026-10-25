import { useEffect, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { displayRecognition, displayRetailerEvidenceMessage, displaySource } from './offCandidatePresentation'

const columns = [
  { key: 'rank', label: 'Rangnummer', header: <span className="rz-external-off-visually-hidden">Rangnummer</span>, width: 58, align: 'right', sortable: true },
  { key: 'product_name', label: 'Artikel', width: 280, sortable: true, filterable: true },
  { key: 'brand', label: 'Merk', width: 150, sortable: true, filterable: true },
  { key: 'source', label: 'Bron', width: 125, sortable: true, filterable: true },
  { key: 'evidence_label', label: 'Herkenning', width: 210, sortable: true, filterable: true },
  { key: 'gtin', label: 'Barcode', width: 170, sortable: true, filterable: true },
  { key: 'quantity', label: 'Inhoud', width: 140, sortable: true, filterable: true },
  { key: 'match', label: 'Overeenkomst', width: 140, align: 'right', sortable: true,
    renderCell: (row) => `${Math.round(row.match * 100)}%` },
]

export default function OffCandidatePanel({ item }) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [evidence, setEvidence] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setResults([])
    setError('')
    setEvidence(null)
    async function search() {
      try {
        // Source identity and store evidence are resolved by the backend.
        const response = await fetchJsonWithAuth('/api/external-databases/products/search-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
          body: JSON.stringify({ receipt_item_id: item.id, mode: 'automatic', limit: 20 }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Open Food Facts kon niet worden geraadpleegd.')
        if (active) setEvidence(payload.retailer_evidence || null)
        if (payload.provider === 'unavailable') throw new Error('Open Food Facts is tijdelijk niet bereikbaar. Probeer opnieuw.')
        if (active) setResults((Array.isArray(payload.results) ? payload.results : []).map((row, index) => ({
          ...row, rank: index + 1, source: displaySource(row.source),
          evidence_label: displayRecognition(row.evidence_label),
          match: Number(row.automatic_rank_score ?? row.score) || 0,
        })))
      } catch (err) {
        if (active && err.name !== 'AbortError') setError(err.message || 'Open Food Facts kon niet worden geraadpleegd.')
      } finally {
        if (active) setLoading(false)
      }
    }
    search()
    return () => { active = false; controller.abort() }
  }, [item, attempt])

  const evidenceMessage = displayRetailerEvidenceMessage(evidence)
  const hasEvidence = evidence && Boolean(evidenceMessage || evidence.product_name || evidence.description
    || evidence.article_number || evidence.gtins?.length || evidence.source_url)

  return (
    <section className="rz-external-receipt-detail" aria-labelledby="off-candidate-heading" data-testid="external-databases-2-off-panel" aria-busy={loading}>
      <div className="rz-external-databases-card rz-external-databases-card--off">
        <h3 id="off-candidate-heading">Productkandidaten voor {item.receipt_line_text} — {item.retailer}</h3>
        <p>Productgegevens van Albert Heijn, Jumbo en Lidl waar beschikbaar, aangevuld met Open Food Facts (OFF). Zoeken slaat niets op.</p>
        {hasEvidence ? <div data-testid="retailer-product-evidence">
          {evidenceMessage ? <p>{evidenceMessage}</p> : null}
          {evidence.product_name ? <p>{evidence.product_name}{evidence.brand ? ` — ${evidence.brand}` : ''}</p> : null}
          {evidence.description ? <p>{evidence.description}</p> : null}
          {evidence.article_number ? <p>{evidence.source || 'Lidl'}-artikelnummer: {evidence.article_number}</p> : null}
          {evidence.gtins?.length ? <p>Barcode{evidence.gtins.length > 1 ? 's' : ''} vermeld door {evidence.source || 'Lidl'}: {evidence.gtins.join(', ')}</p> : null}
          {evidence.source_url ? <a href={evidence.source_url} target="_blank" rel="noopener noreferrer">Bekijk product bij {evidence.source || 'Lidl'}</a> : null}
        </div> : null}
        {loading ? <p role="status">Kandidaten zoeken bij de winkel en in Open Food Facts...</p> : null}
        {error ? <div role="alert"><p>{error}</p><Button type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Opnieuw zoeken</Button></div> : null}
        {!loading && !error ? <DataTable
          columns={columns}
          data={results}
          pageSize={7}
          getRowKey={(row) => row.gtin}
          defaultSort={{ key: 'rank', direction: 'asc' }}
          emptyMessage="Geen passende productkandidaten gevonden."
          dataTestId="external-databases-2-off-candidates"
        /> : null}
      </div>
    </section>
  )
}
