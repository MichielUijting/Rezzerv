import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './externalDatabases.css'

const columns = [
  { key: 'rank', label: 'Nr.', width: 62, align: 'right', sortable: true },
  { key: 'product_name', label: 'Artikel', width: 320, sortable: true },
  { key: 'brand', label: 'Merk', width: 180, sortable: true },
  { key: 'gtin', label: 'Barcode', width: 180, sortable: true },
  { key: 'quantity', label: 'Inhoud', width: 155, sortable: true },
  { key: 'score', label: 'Overeenkomst', width: 145, align: 'right', sortable: true,
    renderCell: (row) => `${Math.round((Number(row.score) || 0) * 100)}%` },
]

export default function OffManualSearchPage() {
  const { receiptItemId = '' } = useParams()
  const { state } = useLocation()
  const navigate = useNavigate()
  const [item, setItem] = useState(() => state?.item?.id === receiptItemId ? state.item : null)
  const [itemError, setItemError] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [searchedQuery, setSearchedQuery] = useState('')
  const [error, setError] = useState('')
  const searchController = useRef(null)

  useEffect(() => () => searchController.current?.abort(), [])

  useEffect(() => {
    if (item?.id === receiptItemId) return undefined
    const controller = new AbortController()
    async function restoreSelectedItem() {
      try {
        const response = await fetchJsonWithAuth('/api/external-databases/unlinked-articles', {
          method: 'GET', signal: controller.signal,
        })
        if (!response.ok) throw new Error('Het artikel is niet beschikbaar.')
        const payload = await response.json()
        const found = (payload.items || []).find((candidate) => candidate.id === receiptItemId)
        if (!found) throw new Error('Het artikel is niet meer beschikbaar in deze lijst.')
        if (!controller.signal.aborted) setItem(found)
      } catch (err) {
        if (!controller.signal.aborted) setItemError(err.message || 'Het artikel kon niet worden geladen.')
      }
    }
    restoreSelectedItem()
    return () => controller.abort()
  }, [item, receiptItemId])

  function goBack() {
    navigate('/externe-databases-2', { state: { selectedItemId: receiptItemId } })
  }

  async function search(event) {
    event.preventDefault()
    const searchText = query.trim()
    if (!item || !searchText || loading) return
    setLoading(true)
    setError('')
    setResults([])
    setSearched(false)
    const controller = new AbortController()
    searchController.current = controller
    try {
      // The backend verifies the original receipt-item identity. This endpoint is read-only.
      const response = await fetchJsonWithAuth('/api/external-products/off/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ receipt_item_id: receiptItemId, mode: 'manual', query: searchText, limit: 20 }),
      })
      const payload = await response.json().catch(() => ({}))
      if (controller.signal.aborted) return
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Zoeken in OFF is niet gelukt.')
      if (payload.provider === 'unavailable') throw new Error('Open Food Facts is tijdelijk niet bereikbaar. Probeer opnieuw.')
      setResults((Array.isArray(payload.results) ? payload.results : []).map((candidate, index) => ({
        ...candidate, rank: index + 1,
      })))
      setSearchedQuery(searchText)
      setSearched(true)
    } catch (err) {
      if (!controller.signal.aborted) setError(err.message || 'Zoeken in OFF is niet gelukt.')
    } finally {
      if (searchController.current === controller) searchController.current = null
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <AppShell title="Zelf zoeken in OFF" showExit={false}>
      <ScreenCard fullWidth>
        <div className="rz-external-off-manual-header">
          <Button type="button" variant="secondary" onClick={goBack}>Terug</Button>
        </div>
        {itemError ? <p role="alert">{itemError}</p> : null}
        {item ? <>
          <p>Artikel: {item.receipt_line_text}</p>
          <form className="rz-external-off-manual-form" onSubmit={search} data-testid="external-off-free-search-form">
            <label className="rz-input-field">
              <span className="rz-label">Zoektekst in OFF</span>
              <input className="rz-input" type="text" autoFocus aria-label="Zoektekst in OFF" value={query}
                onChange={(event) => setQuery(event.target.value)} placeholder="Typ een productnaam, merk of trefwoorden" />
            </label>
            <Button type="submit" disabled={!query.trim() || loading}>{loading ? 'Zoeken...' : 'Zoeken'}</Button>
          </form>
          {loading ? <p role="status">Zoeken in Open Food Facts...</p> : null}
          {error ? <p role="alert">{error}</p> : null}
          {searched && !loading && !error ? <section aria-label="OFF-zoekresultaten">
            <h3>Resultaten uit OFF</h3>
            <DataTable
              key={searchedQuery}
              columns={columns}
              data={results}
              pageSize={7}
              getRowKey={(row) => row.gtin}
              defaultSort={{ key: 'rank', direction: 'asc' }}
              emptyMessage="Geen kandidaten gevonden in Open Food Facts."
              dataTestId="external-off-free-search-results"
            />
          </section> : null}
        </> : !itemError ? <p role="status">Artikel laden...</p> : null}
      </ScreenCard>
    </AppShell>
  )
}
