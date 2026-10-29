import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import Select from '../../ui/Select.jsx'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import './synonymAnalysis.css'

const API = '/api/external-databases/article-synonyms'
const BUCKETS = [
  { key: '0', label: '0 synoniemen' },
  { key: '1', label: '1 synoniem' },
  { key: '2', label: '2 synoniemen' },
  { key: '3+', label: '3 of meer synoniemen' },
]
const productName = (value) => [value?.name, value?.brand, value?.variant].filter(Boolean).join(' · ')
const productSize = (value) => [value?.size_value, value?.size_unit].filter(Boolean).join(' ')

export default function SynonymAnalysisPage() {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [bucket, setBucket] = useState('')
  const [category, setCategory] = useState('')
  const [store, setStore] = useState('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [candidates, setCandidates] = useState([])
  const [candidateId, setCandidateId] = useState('')
  const [candidateLoading, setCandidateLoading] = useState(false)
  const [candidateError, setCandidateError] = useState('')
  const [saving, setSaving] = useState(false)
  const [reloadCandidates, setReloadCandidates] = useState(0)
  const savingRef = useRef(false)

  const refreshAnalysis = useCallback(async (signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis`, { signal })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Synoniemenanalyse kon niet worden geladen.')
    setData(result)
    return result
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    refreshAnalysis(controller.signal)
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [refreshAnalysis])

  useEffect(() => {
    if (!selectedId) {
      setCandidates([])
      setCandidateId('')
      setCandidateError('')
      return undefined
    }
    const controller = new AbortController()
    setCandidateLoading(true)
    setCandidates([])
    setCandidateId('')
    setCandidateError('')
    async function load() {
      try {
        const response = await fetchJsonWithAuth(`${API}/analysis/${encodeURIComponent(selectedId)}/candidates`, { signal: controller.signal })
        const result = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(result.detail || 'Kandidaten konden niet worden geladen.')
        if (!controller.signal.aborted) setCandidates((result.items || []).slice(0, 5))
      } catch (err) {
        if (!controller.signal.aborted) setCandidateError(err.message || 'Kandidaten konden niet worden geladen.')
      } finally {
        if (!controller.signal.aborted) setCandidateLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [selectedId, reloadCandidates])

  const products = data?.items || []
  const selectedProduct = products.find((item) => item.id === selectedId) || null
  const categoryOptions = useMemo(() => [
    { value: '', label: 'Alle artikelsoorten' },
    ...Array.from(new Map(products.map((row) => [row.group_key, {
      value: row.group_key, label: row.group_label,
    }])).values()).sort((a, b) => a.label.localeCompare(b.label, 'nl')),
  ], [products])
  const storeOptions = useMemo(() => [
    { value: '', label: 'Alle winkels' },
    ...[...new Set(products.map((p) => p.store))].sort().map((name) => ({ value: name, label: name })),
  ], [products])
  const visibleProducts = products.filter((item) => (
    (!bucket || (bucket === '3+' ? item.synonym_count >= 3 : item.synonym_count === Number(bucket)))
    && (!category || item.group_key === category)
    && (!store || item.store === store)
    && (!search || [item.name, item.brand, item.variant, item.store, item.group_label]
      .join(' ').toLocaleLowerCase('nl-NL').includes(search.toLocaleLowerCase('nl-NL')))
  ))

  function toggleBucket(value) {
    setBucket((current) => current === value ? '' : value)
    setSelectedId('')
  }

  async function saveCandidate(candidate) {
    if (!candidate || !selectedId || savingRef.current || candidateLoading) return
    if (candidate.left.id !== selectedId && candidate.right.id !== selectedId) return
    savingRef.current = true
    setSaving(true)
    setCandidateError('')
    try {
      const response = await fetchJsonWithAuth(`${API}/link`, {
        method: 'POST',
        body: JSON.stringify({ selections: [{
          left_product_id: candidate.left.id,
          right_product_id: candidate.right.id,
          fingerprint: candidate.fingerprint,
        }] }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || 'Koppelen is niet gelukt.')
      // The canonical link is visible for BOTH products through the fresh
      // server-derived Catalogus/analysis projections. No product/GTIN merge.
      await refreshAnalysis()
      setReloadCandidates((current) => current + 1)
      showFeedback({
        variant: 'success',
        message: result.linked ? 'Synoniem gekoppeld. Beide Catalogusartikelen zijn bijgewerkt.' : 'Dit synoniem was al gekoppeld.',
      })
    } catch (err) {
      setCandidateError(err.message || 'Koppelen is niet gelukt. Vernieuw en probeer opnieuw.')
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const mainColumns = [
    { key: 'name', label: 'Artikel', width: 320, sortable: true, filterable: true },
    { key: 'store', label: 'Winkel', width: 175, sortable: true, filterable: true },
    { key: 'group_label', label: 'Artikelsoort', width: 245, sortable: true, filterable: true },
    { key: 'synonym_count', label: 'Synoniemen', width: 115, sortable: true, align: 'right' },
    { key: 'synonym_names', label: 'Gekoppeld met', width: 280, renderCell: (item) =>
      item.synonym_names?.length ? item.synonym_names.join(', ') : 'Nog geen synoniemen' },
  ]
  const candidateColumns = [
    { key: 'select', label: '', width: 48 },
    { key: 'name', label: 'Kandidaatartikel', width: 295 },
    { key: 'store', label: 'Winkel', width: 165 },
    { key: 'size', label: 'Inhoud / variant', width: 195 },
    { key: 'warning', label: 'Controle', width: 320 },
  ]

  return <AppShell title="Synoniemenanalyse" showExit={false}>
    <ScreenCard fullWidth>
      <div className="rz-synonym-analysis" data-testid="synonym-analysis-page">
         {loading ? <p role="status">Synoniemenanalyse laden…</p> : null}
        {error ? <p role="alert" className="rz-inline-feedback rz-inline-feedback--error">{error}</p> : null}
        {!loading && !error && data ? <>
          <div className="rz-synonym-analysis-summary" aria-label="Filter op aantal synoniemen">
            {BUCKETS.map(({ key, label }) =>
              <button type="button" key={key} className="rz-synonym-analysis-stat"
                aria-pressed={bucket === key} data-testid={`synonym-count-${key.replace('+', 'plus')}`}
                onClick={() => toggleBucket(key)}>
                <strong>{data.summary.synonym_buckets?.[key] ?? 0}</strong>
                <span>{label}</span>
              </button>)}
          </div>
          <div className="rz-synonym-analysis-filters">
            <label>Artikelsoort<Select value={category} onChange={setCategory} options={categoryOptions} ariaLabel="Filter artikelsoort" /></label>
            <label>Winkel<Select value={store} onChange={setStore} options={storeOptions} ariaLabel="Filter winkel" /></label>
            <label>Zoek artikel<input className="rz-input" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Artikel, merk of winkel" /></label>
          </div>
          <DataTable columns={mainColumns} data={visibleProducts} pageSize={10}
            dataTestId="synonym-analysis-items" emptyMessage="Geen artikelen voor dit filter."
            renderRow={(item) => (
              <tr key={item.id} tabIndex={0} className="rz-synonym-analysis-main-row"
                data-testid={`synonym-analysis-open-${item.id}`}
                aria-selected={selectedId === item.id}
                aria-label={`Kandidaten voor ${item.name} openen`}
                title="Dubbelklik om kandidaten te bekijken"
                onDoubleClick={() => setSelectedId(item.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    setSelectedId(item.id)
                  }
                }}>
                <td><div className="rz-synonym-analysis-product">
                  <CatalogProductImage imageUrl={item.image_url} productName={item.name} compact />
                  <span>{item.name}</span>
                </div></td>
                <td>{item.store}</td>
                <td>{item.group_label}</td>
                <td className="rz-num">{item.synonym_count}</td>
                <td>{item.synonym_names?.length ? item.synonym_names.join(', ') : 'Nog geen synoniemen'}</td>
              </tr>
            )} />
          {selectedProduct ? <section className="rz-synonym-analysis-details" data-testid="synonym-analysis-candidates">
            <div className="rz-synonym-analysis-details-heading">
              <h3>Kandidaten voor {selectedProduct.name}</h3>
              <Button type="button" variant="secondary" onClick={() => setSelectedId('')}>Sluiten</Button>
            </div>
            {candidateError ? <p role="alert" className="rz-inline-feedback rz-inline-feedback--error">{candidateError}</p> : null}
            {candidateLoading ? <p role="status">Kandidaten zoeken…</p> : null}
            <DataTable columns={candidateColumns} data={candidates} pageSize={5}
              dataTestId="synonym-analysis-candidate-table"
              emptyMessage={candidateLoading ? 'Kandidaten laden...' : selectedProduct.retailer_code ? 'Geen geschikte kandidaten gevonden met de aanwezige Catalogusgegevens.' : 'De winkel van dit artikel is onbekend. Daardoor kan Inhuis nog geen betrouwbare winkeloverstijgende kandidaten voorstellen.'}
              renderRow={(pair) => {
                const other = pair.left.id === selectedProduct.id ? pair.right : pair.left
                return <tr key={pair.id} className="rz-synonym-analysis-candidate-row"
                  aria-selected={candidateId === pair.id}
                  data-testid={`synonym-candidate-${other.id}`}
                  onDoubleClick={() => saveCandidate(pair)}>
                  <td className="rz-check">
                    <input type="radio" name="synonym-candidate-selection"
                      aria-label={`Selecteer ${other.name} als synoniem`}
                      checked={candidateId === pair.id}
                      disabled={saving || candidateLoading}
                      onChange={() => setCandidateId(pair.id)} />
                  </td>
                  <td><div className="rz-synonym-analysis-product">
                    <CatalogProductImage imageUrl={other.image_url} productName={other.name} compact />
                    <span>{productName(other)}</span>
                  </div></td>
                  <td>{other.store_name}</td>
                  <td>{[productSize(other), other.variant].filter(Boolean).join(' · ') || 'Niet vastgelegd'}</td>
                  <td>{pair.warning || 'Controleer de kenmerken'}</td>
                </tr>
              }} />
            <div className="rz-synonym-analysis-actions">
              <span aria-live="polite">{candidateId ? '1 kandidaat geselecteerd' : ''}</span>
              <Button type="button" disabled={!candidateId || saving || candidateLoading}
                onClick={() => saveCandidate(candidates.find((pair) => pair.id === candidateId))}
                data-testid="synonym-analysis-confirm">
                {saving ? 'Koppelen...' : 'Merk kandidaat aan als synoniem'}
              </Button>
            </div>
          </section> : null}
        </> : null}
      </div>
    </ScreenCard>
  </AppShell>
}
