import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import DataTable from '../../ui/DataTable'
import { fetchJsonWithAuth } from '../../lib/authSession'

const columns = [
  { key: 'brick_code', label: 'GS1-code', width: 125, sortable: true },
  { key: 'brick_description', label: 'Nederlandse GS1-omschrijving', width: 320, sortable: true },
  { key: 'family_description', label: 'Productfamilie', width: 250, sortable: true },
]

function errorText(data, fallback) {
  return typeof data?.detail === 'string' && data.detail.trim() ? data.detail : fallback
}

export default function Ed2GpcClassificationPanel({ item, onClassified }) {
  const [suggestions, setSuggestions] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [hasSearched, setHasSearched] = useState(false)
  const [selectedBrick, setSelectedBrick] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirmSave, setConfirmSave] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      setSelectedBrick(null)
      try {
        if (!item.pending_global_product_id || !item.off_link_id) {
          throw new Error('Het nog te classificeren Catalogusproduct ontbreekt. Vernieuw het overzicht.')
        }
        const response = await fetchJsonWithAuth(
          `/api/catalog/${encodeURIComponent(item.pending_global_product_id)}/gpc-brick`,
          { signal: controller.signal },
        )
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(errorText(payload, 'GS1-voorstellen konden niet worden geladen.'))
        const candidates = payload.assignment ? [payload.assignment]
          : Array.isArray(payload.suggestions) ? payload.suggestions : []
        if (active) setSuggestions(candidates.slice(0, 5))
      } catch (err) {
        if (active && err.name !== 'AbortError') setError(err.message || 'GS1-voorstellen konden niet worden geladen.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false; controller.abort() }
  }, [item.pending_global_product_id, item.off_link_id])

  async function searchBricks(event) {
    event.preventDefault()
    const query = searchQuery.trim()
    if (!query || searching) return
    setSearching(true)
    setHasSearched(true)
    setSearchResults([])
    setSelectedBrick(null)
    setError('')
    try {
      const response = await fetchJsonWithAuth(`/api/catalog/gpc/bricks?query=${encodeURIComponent(query)}&limit=25`)
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(errorText(payload, 'De officiële GS1-catalogus kon niet worden doorzocht.'))
      setSearchResults(Array.isArray(payload.items) ? payload.items : [])
    } catch (err) {
      setError(err.message || 'De officiële GS1-catalogus kon niet worden doorzocht.')
    } finally {
      setSearching(false)
    }
  }

  async function confirmClassification() {
    if (!selectedBrick || saving || !item.off_link_id) return
    setConfirmSave(false)
    setSaving(true)
    setError('')
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/off/classify-pending', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          receipt_item_id: item.id,
          link_id: item.off_link_id,
          brick_code: selectedBrick.brick_code,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.ok !== true || payload.linked !== true
          || payload.gpc_brick_code !== selectedBrick.brick_code) {
        throw new Error(errorText(payload, 'GS1-classificatie is niet bevestigd.'))
      }
      onClassified?.(`GS1-classificatie ${selectedBrick.brick_code} vastgelegd; het bonartikel is gekoppeld.`)
    } catch (err) {
      setError(err.name === 'AbortError'
        ? 'Opslaan niet bevestigd. Vernieuw ED2 om de actuele status te controleren.'
        : errorText({ detail: err.message }, 'GS1-classificatie is niet bevestigd.'))
    } finally {
      window.clearTimeout(timeout)
      setSaving(false)
    }
  }

  const candidates = hasSearched ? searchResults : suggestions

  return (
    <section className="rz-external-receipt-detail" data-testid="ed2-gpc-panel">
      <div className="rz-external-databases-card rz-external-databases-card--off">
        <h3>GS1-classificatie aanvullen</h3>
        <p>Artikel: <strong>{item.receipt_line_text}</strong> — {item.retailer}</p>
        <p>Kies de juiste officiële Nederlandse GS1 GPC Brick. De classificatie geldt voor dit centrale Catalogusproduct en eventuele andere bonartikelen die eraan gekoppeld zijn.</p>
        {loading ? <p role="status">Waarschijnlijke GS1-classificaties laden...</p> : null}
        {!loading && !hasSearched && suggestions.length ? <p>Waarschijnlijke GS1-classificaties (nog niet bevestigd):</p> : null}
        <form className="rz-external-off-manual-form" onSubmit={searchBricks}>
          <label className="rz-input-field">
            <span className="rz-label">Zoeken op GS1-code of productnaam</span>
            <input className="rz-input" value={searchQuery} disabled={saving}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Bijvoorbeeld melk of 1000..." />
          </label>
          <Button type="submit" disabled={searching || saving || !searchQuery.trim()}>
            {searching ? 'Zoeken...' : 'Zoeken'}
          </Button>
        </form>
        {error ? <p role="alert" onClick={() => setError('')} tabIndex={0}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setError('') }}>
          {error}</p> : null}
        {!loading && !searching && !candidates.length ? <p>Geen passende GS1-classificatie gevonden. Probeer een andere zoekterm.</p> : null}
        {!loading && !searching && candidates.length ? <DataTable
          columns={columns}
          data={candidates}
          pageSize={7}
          getRowKey={(row) => row.brick_code}
          defaultSort={{ key: 'brick_description', direction: 'asc' }}
          dataTestId="ed2-gpc-candidates"
          renderRow={(row) => <tr key={row.brick_code}
            tabIndex={0} aria-selected={selectedBrick?.brick_code === row.brick_code}
            className={selectedBrick?.brick_code === row.brick_code ? 'rz-row-selected' : ''}
            onClick={() => { if (!saving) setSelectedBrick(row) }}
            onKeyDown={(event) => { if (event.target === event.currentTarget
                && (event.key === 'Enter' || event.key === ' ')) {
              event.preventDefault(); if (!saving) setSelectedBrick(row)
            } }}>
            {columns.map((column) => <td key={column.key}>{row[column.key] || '—'}</td>)}
          </tr>}
        /> : null}
        {selectedBrick ? <p data-testid="ed2-gpc-selected">Gekozen: <strong>{selectedBrick.brick_code} — {selectedBrick.brick_description}</strong></p> : null}
        <div className="rz-external-databases-actions">
          <Button type="button" disabled={!selectedBrick || saving || searching || loading}
            onClick={() => setConfirmSave(true)}>
            {saving ? 'Opslaan...' : 'Classificatie opslaan'}
          </Button>
        </div>
      </div>
      {confirmSave ? <div className="rz-modal-backdrop">
        <div className="rz-modal-card" role="alertdialog" aria-modal="true" aria-labelledby="ed2-gpc-confirm">
          <p className="rz-modal-text" id="ed2-gpc-confirm">
            Weet u zeker dat u GS1-classificatie {selectedBrick?.brick_code} wilt vastleggen voor dit Catalogusproduct?
          </p>
          <div className="rz-modal-actions">
            <Button type="button" variant="secondary" onClick={() => setConfirmSave(false)}>Annuleren</Button>
            <Button type="button" onClick={confirmClassification}>OK</Button>
          </div>
        </div>
      </div> : null}
    </section>
  )
}
