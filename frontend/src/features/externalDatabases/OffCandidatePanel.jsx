import { useEffect, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

const columns = [
  { key: 'rank', label: 'Voorkeur', width: 90, align: 'right', sortable: true },
  { key: 'product_name', label: 'Artikel', width: 280, sortable: true, filterable: true },
  { key: 'brand', label: 'Merk', width: 150, sortable: true, filterable: true },
  { key: 'gtin', label: 'Barcode', width: 170, sortable: true, filterable: true },
  { key: 'quantity', label: 'Inhoud', width: 140, sortable: true, filterable: true },
  { key: 'match', label: 'Overeenkomst', width: 140, align: 'right', sortable: true,
    renderCell: (row) => `${Math.round(row.match * 100)}%` },
]

export default function OffCandidatePanel({ item }) {
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
        // Same automatic flow as Externe databases: resolve the source by ID,
        // then apply existing query variants, retailer affinity and ranking.
        const response = await fetchJsonWithAuth('/api/external-products/off/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
          body: JSON.stringify({ receipt_item_id: item.id, mode: 'automatic', limit: 20 }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Open Food Facts kon niet worden geraadpleegd.')
        if (payload.provider === 'unavailable') throw new Error('Open Food Facts is tijdelijk niet bereikbaar. Probeer opnieuw.')
        if (active) setResults((Array.isArray(payload.results) ? payload.results : []).map((row, index) => ({
          ...row, rank: index + 1, match: Number(row.automatic_rank_score ?? row.score) || 0,
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
      <div className="rz-external-databases-card">
        <h3 id="off-candidate-heading">OFF-kandidaten voor {item.receipt_line_text} — {item.retailer}</h3>
        <p>Best passende suggesties uit Open Food Facts, op volgorde van voorkeur.</p>
        {loading ? <p role="status">Kandidaten zoeken in Open Food Facts...</p> : null}
        {error ? <div role="alert"><p>{error}</p><Button type="button" variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Opnieuw zoeken</Button></div> : null}
        {!loading && !error ? <DataTable
          columns={columns}
          data={results}
          getRowKey={(row) => row.gtin}
          defaultSort={{ key: 'rank', direction: 'asc' }}
          emptyMessage="Geen passende OFF-kandidaten gevonden."
          dataTestId="external-databases-2-off-candidates"
        /> : null}
      </div>
    </section>
  )
}
