import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Table from '../../ui/Table.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const SOURCE_LABELS = {
  household_article: 'Huishoudartikel',
  product_type: 'Producttype',
  article_group: 'Artikelgroep',
}

const SOURCE_GROUPS = [
  ['household_article', 'Huishoudartikelen'],
  ['product_type', 'Producttypen'],
  ['article_group', 'Artikelgroepen'],
]

const FILTER_CONTROL_STYLE = {
  width: '100%',
  minWidth: 0,
  boxSizing: 'border-box',
  color: '#1f2937',
  backgroundColor: '#ffffff',
  WebkitTextFillColor: '#1f2937',
}

const SORT_FIELDS = {
  checked: (item) => (item.checked ? 1 : 0),
  article: (item) => String(item.article_name || ''),
  articleGroup: (item) => String(item.article_group_name || ''),
  productType: (item) => String(item.product_type_name || ''),
  size: (item) => String(item.size || ''),
  note: (item) => String(item.note || ''),
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  if (response.status === 204) return null
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : 'Verzoek mislukt'
    throw new Error(detail)
  }
  return payload
}

function filterOptions(items, field) {
  return [...new Set((items || []).map((item) => String(item?.[field] || '').trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'nl'))
}

function SortableHeader({ field, label, sort, onSort }) {
  const active = sort.field === field
  const indicator = active ? (sort.direction === 'asc' ? '^' : 'v') : ''
  return (
    <th aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" onClick={() => onSort(field)} aria-label={`Sorteer op ${label}`} style={{ appearance: 'none', border: 0, background: 'transparent', color: 'inherit', font: 'inherit', fontWeight: 'inherit', padding: 0, width: '100%', textAlign: 'left', cursor: 'pointer' }}>
        {label}{indicator ? ` ${indicator}` : ''}
      </button>
    </th>
  )
}

export default function ShoppingPage() {
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogResults, setCatalogResults] = useState([])
  const [selectedResultId, setSelectedResultId] = useState('')
  const [filters, setFilters] = useState({ checked: 'all', article: '', articleGroup: '', productType: '' })
  const [sort, setSort] = useState({ field: 'article', direction: 'asc' })
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadList() {
    setLoading(true)
    setError('')
    try { setList(await requestJson('/api/shopping-list')) }
    catch (loadError) { setError(loadError?.message || 'Winkellijst kon niet worden geladen.') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadList() }, [])

  useEffect(() => {
    const query = catalogQuery.trim()
    setSelectedResultId('')
    if (query.length < 2) { setCatalogResults([]); return undefined }
    const timer = window.setTimeout(async () => {
      setSearching(true)
      setError('')
      try {
        const payload = await requestJson(`/api/shopping-list/catalog-search?scope=all&query=${encodeURIComponent(query)}`)
        setCatalogResults(Array.isArray(payload?.items) ? payload.items : [])
      } catch (searchError) {
        setCatalogResults([])
        setError(searchError?.message || 'Artikelen konden niet worden doorzocht.')
      } finally { setSearching(false) }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [catalogQuery])

  const selectedResult = useMemo(() => catalogResults.find((item) => `${item.source_type}:${item.source_id}` === selectedResultId) || null, [catalogResults, selectedResultId])
  const groupedResults = useMemo(() => SOURCE_GROUPS.map(([sourceType, label]) => ({ sourceType, label, items: catalogResults.filter((item) => item.source_type === sourceType) })).filter((group) => group.items.length > 0), [catalogResults])
  const articleGroupOptions = useMemo(() => filterOptions(list.items, 'article_group_name'), [list.items])
  const productTypeOptions = useMemo(() => filterOptions(list.items, 'product_type_name'), [list.items])

  const visibleItems = useMemo(() => {
    const filtered = (list.items || []).filter((item) => {
      if (filters.checked === 'open' && item.checked) return false
      if (filters.checked === 'checked' && !item.checked) return false
      if (filters.article && !String(item.article_name || '').toLowerCase().includes(filters.article.toLowerCase())) return false
      if (filters.articleGroup && String(item.article_group_name || '') !== filters.articleGroup) return false
      if (filters.productType && String(item.product_type_name || '') !== filters.productType) return false
      return true
    })
    const selector = SORT_FIELDS[sort.field] || SORT_FIELDS.article
    const direction = sort.direction === 'desc' ? -1 : 1
    return [...filtered].sort((left, right) => {
      const leftValue = selector(left)
      const rightValue = selector(right)
      if (typeof leftValue === 'number' && typeof rightValue === 'number') return (leftValue - rightValue) * direction
      return String(leftValue).localeCompare(String(rightValue), 'nl', { numeric: true, sensitivity: 'base' }) * direction
    })
  }, [list.items, filters, sort])

  function changeSort(field) {
    setSort((current) => ({ field, direction: current.field === field && current.direction === 'asc' ? 'desc' : 'asc' }))
  }

  async function addSelectedResult() {
    if (!selectedResult) { setError('Selecteer eerst een zoekresultaat.'); return }
    setSaving(true); setError(''); setMessage('')
    try {
      await requestJson('/api/shopping-list/items', { method: 'POST', body: JSON.stringify({ article_name: selectedResult.article_name || selectedResult.label, article_group_name: selectedResult.article_group_name || '', product_type_name: selectedResult.product_type_name || '', source_type: selectedResult.source_type, source_id: selectedResult.source_id }) })
      setMessage(`${selectedResult.label} toegevoegd aan de winkellijst.`)
      setCatalogQuery(''); setCatalogResults([]); setSelectedResultId('')
      await loadList()
    } catch (saveError) { setError(saveError?.message || 'Het geselecteerde resultaat kon niet worden toegevoegd.') }
    finally { setSaving(false) }
  }

  async function updateItem(item, patch) {
    setSaving(true); setError('')
    try { await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify(patch) }); await loadList() }
    catch (saveError) { setError(saveError?.message || 'Winkellijstregel kon niet worden bijgewerkt.'); await loadList() }
    finally { setSaving(false) }
  }

  function updateChecked(item, checked) {
    setList((current) => ({ ...current, items: (current.items || []).map((currentItem) => currentItem.id === item.id ? { ...currentItem, checked } : currentItem) }))
    void updateItem(item, { checked })
  }

  async function completeShopping() {
    if (!window.confirm('De actuele winkellijst wordt leeggemaakt. Voorraad en bronlijsten blijven ongewijzigd.')) return
    setSaving(true); setError(''); setMessage('')
    try { await requestJson('/api/shopping-list/complete', { method: 'POST' }); setMessage('Winkelen is afgerond. De winkellijst is leeggemaakt.'); await loadList() }
    catch (completeError) { setError(completeError?.message || 'Winkelen kon niet worden afgerond.') }
    finally { setSaving(false) }
  }

  const inlineInputStyle = { width: '100%', minWidth: 0, boxSizing: 'border-box' }
  const tableStyle = { tableLayout: 'fixed', width: '1120px', minWidth: '1120px' }

  return (
    <AppShell title="Winkelen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: 18, width: '100%' }} data-testid="shopping-page">
          <div>
            <h2 style={{ margin: 0 }}>Inkooplijst — {Number(list.item_count || 0)} artikelen</h2>
            <p style={{ marginBottom: 0, color: '#667085' }}>Zoek tegelijk in Huishoudartikelen, Producttypen en Artikelgroepen. Vul daarna alleen waar nodig aanvullende gegevens in.</p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(280px, 1fr) auto', gap: 12, alignItems: 'stretch' }}>
            <label className="rz-input-field"><span className="rz-label">Artikel zoeken</span><input className="rz-input" value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Zoek artikel, producttype of artikelgroep" aria-label="Artikel zoeken" /></label>
            <label className="rz-input-field"><span className="rz-label">Zoekresultaat</span><select className="rz-input" value={selectedResultId} onChange={(event) => setSelectedResultId(event.target.value)} aria-label="Zoekresultaat" disabled={searching || catalogResults.length === 0}><option value="">{searching ? 'Zoeken…' : catalogResults.length ? 'Selecteer resultaat' : 'Geen resultaten'}</option>{groupedResults.map((group) => <optgroup key={group.sourceType} label={group.label}>{group.items.map((item) => <option key={`${item.source_type}:${item.source_id}`} value={`${item.source_type}:${item.source_id}`}>{item.label} — {SOURCE_LABELS[item.source_type] || item.source_type}</option>)}</optgroup>)}</select></label>
            <Button type="button" onClick={addSelectedResult} disabled={saving || !selectedResult} style={{ alignSelf: 'end' }}>Toevoegen</Button>
          </div>

          {error ? <div role="alert" style={{ color: '#9b1c1c' }}>{error}</div> : null}
          {message ? <div role="status" style={{ color: '#1A3E2B' }}>{message}</div> : null}

          <Table dataTestId="shopping-list-table" resizableColumns tableStyle={tableStyle}>
            <colgroup><col style={{ width: 90 }} /><col style={{ width: 220 }} /><col style={{ width: 180 }} /><col style={{ width: 210 }} /><col style={{ width: 180 }} /><col style={{ width: 240 }} /></colgroup>
            <thead>
              <tr className="rz-table-header"><SortableHeader field="checked" label="Gekocht" sort={sort} onSort={changeSort} /><SortableHeader field="article" label="Artikel" sort={sort} onSort={changeSort} /><SortableHeader field="articleGroup" label="Artikelgroep" sort={sort} onSort={changeSort} /><SortableHeader field="productType" label="Producttype" sort={sort} onSort={changeSort} /><SortableHeader field="size" label="Omvang" sort={sort} onSort={changeSort} /><SortableHeader field="note" label="Opmerking" sort={sort} onSort={changeSort} /></tr>
              <tr><th><select className="rz-input" style={FILTER_CONTROL_STYLE} value={filters.checked} onChange={(event) => setFilters((current) => ({ ...current, checked: event.target.value }))} aria-label="Filter gekocht"><option value="all">Filter</option><option value="open">Nog te kopen</option><option value="checked">Gekocht</option></select></th><th><input className="rz-input" style={FILTER_CONTROL_STYLE} value={filters.article} onChange={(event) => setFilters((current) => ({ ...current, article: event.target.value }))} placeholder="Zoeken" aria-label="Zoeken in winkellijst" /></th><th><select className="rz-input" style={FILTER_CONTROL_STYLE} value={filters.articleGroup} onChange={(event) => setFilters((current) => ({ ...current, articleGroup: event.target.value }))} aria-label="Filter artikelgroep"><option value="">Filter</option>{articleGroupOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></th><th><select className="rz-input" style={FILTER_CONTROL_STYLE} value={filters.productType} onChange={(event) => setFilters((current) => ({ ...current, productType: event.target.value }))} aria-label="Filter producttype"><option value="">Filter</option>{productTypeOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></th><th>&nbsp;</th><th>&nbsp;</th></tr>
            </thead>
            <tbody>
              {loading ? <tr><td colSpan={6}>Winkellijst laden…</td></tr> : visibleItems.length === 0 ? <><tr><td colSpan={6}>Nog geen artikelen op de winkellijst.</td></tr><tr><td colSpan={6}>&nbsp;</td></tr><tr><td colSpan={6}>&nbsp;</td></tr></> : visibleItems.map((item) => <tr key={item.id}><td><input type="checkbox" checked={Boolean(item.checked)} onChange={(event) => updateChecked(item, event.target.checked)} aria-label={`Gekocht ${item.article_name}`} style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} /></td><td title={item.article_name}>{item.article_name}</td><td title={item.article_group_name}>{item.article_group_name}</td><td title={item.product_type_name}>{item.product_type_name}</td><td><input className="rz-input" style={inlineInputStyle} defaultValue={item.size || ''} aria-label={`Omvang ${item.article_name}`} onBlur={(event) => updateItem(item, { size: event.target.value })} /></td><td><input className="rz-input" style={inlineInputStyle} defaultValue={item.note || ''} aria-label={`Opmerking ${item.article_name}`} onBlur={(event) => updateItem(item, { note: event.target.value })} /></td></tr>)}
            </tbody>
          </Table>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Button type="button" onClick={completeShopping} disabled={saving || Number(list.item_count || 0) === 0}>Winkelen afgerond</Button></div>
        </div>
      </Card>
    </AppShell>
  )
}
