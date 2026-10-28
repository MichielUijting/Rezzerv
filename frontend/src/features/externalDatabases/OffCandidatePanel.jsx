import { useEffect, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useNavigate } from 'react-router-dom'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { displayRecognition, displaySource } from './offCandidatePresentation'

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
  const navigate = useNavigate()
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setResults([])
    setError('')
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

  return (
    <section className="rz-external-receipt-detail" aria-labelledby="off-candidate-heading" data-testid="external-databases-2-off-panel" aria-busy={loading}>
      <div className="rz-external-databases-card rz-external-databases-card--off">
        <h3 id="off-candidate-heading">Productkandidaten voor {item.receipt_line_text} — {item.retailer}</h3>
        <p>Productgegevens van Albert Heijn, Jumbo en Lidl waar beschikbaar, aangevuld met Open Food Facts (OFF). Zoeken slaat niets op.</p>
        <div className="rz-external-databases-actions">
          <Button type="button" variant="secondary" onClick={() => navigate(`/externe-databases-2/off-zoeken/${encodeURIComponent(item.id)}`, { state: { item } })}>
            Zelf zoeken in OFF
          </Button>
        </div>
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
