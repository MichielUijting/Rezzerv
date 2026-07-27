import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import Table from '../../ui/Table'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'

function resolveHouseholdId(explicitHouseholdId) {
  const explicit = String(explicitHouseholdId || '').trim()
  if (explicit) return explicit
  const contextId = String(readStoredAuthContext()?.active_household_id || '').trim()
  if (contextId) return contextId
  for (const key of ['rezzerv_active_household_id', 'rezzerv_household_id', 'active_household_id']) {
    const value = String(localStorage.getItem(key) || '').trim()
    if (value) return value
  }
  return ''
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || data?.message || 'De Producttypeactie is mislukt')
  return data
}

export default function ProductTypeManualSelectionPanel({ householdId, onError, onMessage }) {
  const effectiveHouseholdId = useMemo(() => resolveHouseholdId(householdId), [householdId])
  const [proposals, setProposals] = useState([])
  const [selectedArticleId, setSelectedArticleId] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selectedBrickCode, setSelectedBrickCode] = useState('')
  const [preview, setPreview] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  async function loadProposals() {
    if (!effectiveHouseholdId) return
    setIsLoading(true)
    try {
      const data = await requestJson(`/api/households/${encodeURIComponent(effectiveHouseholdId)}/product-type-resolution-proposals`, { method: 'GET' })
      const items = Array.isArray(data?.items) ? data.items : []
      setProposals(items)
      if (selectedArticleId && !items.some((item) => String(item.household_article_id) === selectedArticleId)) {
        setSelectedArticleId('')
        setQuery('')
      }
    } catch (error) {
      onError?.(error?.message || 'Onopgeloste Producttypen konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => { void loadProposals() }, [effectiveHouseholdId])

  const selectedArticle = proposals.find((item) => String(item.household_article_id) === selectedArticleId) || null

  function chooseArticle(articleId) {
    const article = proposals.find((item) => String(item.household_article_id) === articleId)
    setSelectedArticleId(articleId)
    setQuery(article ? String(article.inventory_name || '') : '')
    setResults([])
    setSelectedBrickCode('')
    setPreview(null)
  }

  async function searchCatalog(event) {
    event.preventDefault()
    if (!effectiveHouseholdId || !selectedArticleId || !query.trim()) return
    setIsSearching(true)
    setPreview(null)
    setSelectedBrickCode('')
    try {
      const url = `/api/households/${encodeURIComponent(effectiveHouseholdId)}/product-type-catalog-search?household_article_id=${encodeURIComponent(selectedArticleId)}&q=${encodeURIComponent(query.trim())}&limit=25`
      const data = await requestJson(url, { method: 'GET' })
      setResults(Array.isArray(data?.items) ? data.items : [])
    } catch (error) {
      onError?.(error?.message || 'De GPC-catalogus kon niet worden doorzocht')
    } finally {
      setIsSearching(false)
    }
  }

  function buildPreview(item) {
    setSelectedBrickCode(String(item.gpc_brick_code || ''))
    setPreview({ selected_product_type: item, confirmation_status: 'pending' })
  }

  async function confirmSelection() {
    if (!selectedBrickCode || !selectedArticleId || !effectiveHouseholdId) return
    setIsSaving(true)
    try {
      const data = await requestJson(`/api/households/${encodeURIComponent(effectiveHouseholdId)}/product-type-selection/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          household_article_id: selectedArticleId,
          gpc_brick_code: selectedBrickCode,
          confirmed: true,
        }),
      })
      onMessage?.(`Producttype opgeslagen: ${data?.selected_product_type?.display_name || data?.product_type_name || selectedBrickCode}`)
      setSelectedArticleId('')
      setQuery('')
      setResults([])
      setSelectedBrickCode('')
      setPreview(null)
      await loadProposals()
    } catch (error) {
      onError?.(error?.message || 'Het Producttype kon niet worden opgeslagen')
    } finally {
      setIsSaving(false)
    }
  }

  if (!effectiveHouseholdId) {
    return <div className="rz-inline-feedback">Geen actief huishouden beschikbaar voor Producttypeselectie.</div>
  }

  return (
    <section className="rz-product-type-manual-panel" data-testid="product-type-manual-selection-panel">
      <div className="rz-external-databases-section-header">
        <h3>Ontbrekend Producttype aanvullen</h3>
      </div>
      <p className="rz-product-type-manual-explanation">
        Sommige voorraadartikelen hebben nog geen officiële GS1-productindeling. Kies alleen zo’n artikel, zoek het passende Producttype en bevestig de koppeling. Dit verandert geen voorraadhoeveelheden.
      </p>

      {isLoading ? <div className="rz-external-databases-muted">Artikelen zonder Producttype laden...</div> : null}
      {!isLoading && !proposals.length ? <div className="rz-inline-feedback rz-inline-feedback--success">Alle huidige artikelen hebben een Producttype.</div> : null}

      {proposals.length ? (
        <form onSubmit={searchCatalog} className="rz-external-databases-form">
          <div className="rz-external-databases-form-grid">
            <label className="rz-input-field">
              <div className="rz-label">Artikel zonder Producttype</div>
              <select className="rz-input" value={selectedArticleId} onChange={(event) => chooseArticle(event.target.value)}>
                <option value="">Kies eerst een artikel</option>
                {proposals.map((item) => <option key={item.household_article_id} value={item.household_article_id}>{item.inventory_name}</option>)}
              </select>
            </label>
            <Input label="Zoekterm in GS1-catalogus" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Bijvoorbeeld diepvriespizza" disabled={!selectedArticleId} />
          </div>
          <div className="rz-external-databases-actions">
            <Button type="submit" disabled={isSearching || !selectedArticleId || !query.trim()}>{isSearching ? 'Zoeken...' : 'Producttype zoeken'}</Button>
          </div>
        </form>
      ) : null}

      {selectedArticleId && !isSearching && !results.length ? (
        <div className="rz-external-databases-muted">Klik op ‘Producttype zoeken’ om passende officiële GS1-Producttypen te tonen.</div>
      ) : null}

      {results.length ? (
        <div className="rz-product-type-results-wrap">
          <p className="rz-product-type-manual-explanation">Kies het resultaat dat inhoudelijk het beste bij <strong>{selectedArticle?.inventory_name}</strong> past.</p>
          <Table dataTestId="product-type-catalog-search-results" tableClassName="rz-external-databases-table rz-product-type-results-table" resizableColumns={false}>
            <thead><tr className="rz-table-header"><th>Producttype</th><th>Klasse</th><th>Familie</th><th>Brickcode</th><th>Actie</th></tr></thead>
            <tbody>{results.map((item) => (
              <tr key={item.gpc_brick_code}>
                <td>{item.display_name || item.gpc_brick_name}</td>
                <td>{item.gpc_class_name || '-'}</td>
                <td>{item.gpc_family_name || '-'}</td>
                <td>{item.gpc_brick_code}</td>
                <td><Button type="button" variant="secondary" onClick={() => buildPreview(item)}>Kiezen</Button></td>
              </tr>
            ))}</tbody>
          </Table>
        </div>
      ) : null}

      {preview?.selected_product_type ? (
        <div className="rz-product-type-confirmation" role="dialog" aria-label="Producttype bevestigen">
          <p><strong>Controleer de keuze:</strong></p>
          <p><strong>{selectedArticle?.inventory_name || 'Artikel'}</strong> wordt gekoppeld aan <strong>{preview.selected_product_type.display_name || preview.selected_product_type.gpc_brick_name}</strong> ({preview.selected_product_type.gpc_brick_code}).</p>
          <div className="rz-external-databases-actions">
            <Button type="button" onClick={confirmSelection} disabled={isSaving}>{isSaving ? 'Opslaan...' : 'Bevestigen en opslaan'}</Button>
            <Button type="button" variant="secondary" onClick={() => { setPreview(null); setSelectedBrickCode('') }}>Annuleren</Button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
