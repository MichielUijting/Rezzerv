import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Table from '../../ui/Table.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const UNITS = [
  ['', 'Filter'],
  ['stuk', 'stuk'],
  ['stuks', 'stuks'],
  ['gram', 'gram'],
  ['kilogram', 'kilogram'],
  ['milliliter', 'milliliter'],
  ['liter', 'liter'],
  ['verpakking', 'verpakking'],
]

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

export default function ShoppingPage() {
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogResults, setCatalogResults] = useState([])
  const [catalogCounts, setCatalogCounts] = useState({ household_article: 0, product_type: 0, article_group: 0 })
  const [selectedResultId, setSelectedResultId] = useState('')
  const [filters, setFilters] = useState({ checked: 'all', article: '', articleGroup: '', productType: '', unit: '' })
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadList() {
    setLoading(true)
    setError('')
    try {
      setList(await requestJson('/api/shopping-list'))
    } catch (loadError) {
      setError(loadError?.message || 'Winkellijst kon niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadList()
  }, [])

  useEffect(() => {
    const query = catalogQuery.trim()
    setSelectedResultId('')
    if (query.length < 2) {
      setCatalogResults([])
      setCatalogCounts({ household_article: 0, product_type: 0, article_group: 0 })
      return undefined
    }
    const timer = window.setTimeout(async () => {
      setSearching(true)
      setError('')
      try {
        const payload = await requestJson(`/api/shopping-list/catalog-search?scope=all&query=${encodeURIComponent(query)}`)
        setCatalogResults(Array.isArray(payload?.items) ? payload.items : [])
        setCatalogCounts(payload?.counts || { household_article: 0, product_type: 0, article_group: 0 })
      } catch (searchError) {
        setCatalogResults([])
        setCatalogCounts({ household_article: 0, product_type: 0, article_group: 0 })
        setError(searchError?.message || 'Catalogus kon niet worden doorzocht.')
      } finally {
        setSearching(false)
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [catalogQuery])

  const selectedResult = useMemo(
    () => catalogResults.find((item) => `${item.source_type}:${item.source_id}` === selectedResultId) || null,
    [catalogResults, selectedResultId],
  )

  const groupedResults = useMemo(() => SOURCE_GROUPS.map(([sourceType, label]) => ({
    sourceType,
    label,
    items: catalogResults.filter((item) => item.source_type === sourceType),
  })).filter((group) => group.items.length > 0), [catalogResults])

  const articleGroupOptions = useMemo(() => filterOptions(list.items, 'article_group_name'), [list.items])
  const productTypeOptions = useMemo(() => filterOptions(list.items, 'product_type_name'), [list.items])

  const visibleItems = useMemo(() => (list.items || []).filter((item) => {
    if (filters.checked === 'open' && item.checked) return false
    if (filters.checked === 'checked' && !item.checked) return false
    if (filters.article && !String(item.article_name || '').toLowerCase().includes(filters.article.toLowerCase())) return false
    if (filters.articleGroup && String(item.article_group_name || '') !== filters.articleGroup) return false
    if (filters.productType && String(item.product_type_name || '') !== filters.productType) return false
    if (filters.unit && String(item.unit || '') !== filters.unit) return false
    return true
  }), [list.items, filters])

  async function addSelectedResult() {
    if (!selectedResult) {
      setError('Selecteer eerst een zoekresultaat.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/shopping-list/items', {
        method: 'POST',
        body: JSON.stringify({
          article_name: selectedResult.article_name || selectedResult.label,
          article_group_name: selectedResult.article_group_name || '',
          product_type_name: selectedResult.product_type_name || '',
          source_type: selectedResult.source_type,
          source_id: selectedResult.source_id,
        }),
      })
      setMessage(`${selectedResult.label} toegevoegd aan de winkellijst.`)
      setCatalogQuery('')
      setCatalogResults([])
      setCatalogCounts({ household_article: 0, product_type: 0, article_group: 0 })
      setSelectedResultId('')
      await loadList()
    } catch (saveError) {
      setError(saveError?.message || 'Het geselecteerde resultaat kon niet worden toegevoegd.')
    } finally {
      setSaving(false)
    }
  }

  async function updateItem(item, patch) {
    setSaving(true)
    setError('')
    try {
      await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      await loadList()
    } catch (saveError) {
      setError(saveError?.message || 'Winkellijstregel kon niet worden bijgewerkt.')
      await loadList()
    } finally {
      setSaving(false)
    }
  }

  function updateChecked(item, checked) {
    setList((current) => ({
      ...current,
      items: (current.items || []).map((currentItem) => currentItem.id === item.id ? { ...currentItem, checked } : currentItem),
    }))
    void updateItem(item, { checked })
  }

  async function completeShopping() {
    if (!window.confirm('De actuele winkellijst wordt leeggemaakt. Voorraad en bronlijsten blijven ongewijzigd.')) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/shopping-list/complete', { method: 'POST' })
      setMessage('Winkelen is afgerond. De winkellijst is leeggemaakt.')
      await loadList()
    } catch (completeError) {
      setError(completeError?.message || 'Winkelen kon niet worden afgerond.')
    } finally {
      setSaving(false)
    }
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

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(280px, 1fr) auto', gap: 12, alignItems: 'end' }}>
            <label className="rz-input-field">
              <span className="rz-label">Catalogus zoeken</span>
              <input className="rz-input" value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Zoek artikel, producttype of artikelgroep" aria-label="Catalogus zoeken" />
            </label>
            <label className="rz-input-field">
              <span className="rz-label">Zoekresultaat</span>
              <select className="rz-input" value={selectedResultId} onChange={(event) => setSelectedResultId(event.target.value)} aria-label="Zoekresultaat" disabled={searching || catalogResults.length === 0}>
                <option value="">{searching ? 'Zoeken…' : catalogResults.length ? 'Selecteer resultaat' : 'Geen resultaten'}</option>
                {groupedResults.map((group) => (
                  <optgroup key={group.sourceType} label={group.label}>
                    {group.items.map((item) => (
                      <option key={`${item.source_type}:${item.source_id}`} value={`${item.source_type}:${item.source_id}`}>
                        {item.label} — {SOURCE_LABELS[item.source_type] || item.source_type}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <Button type="button" onClick={addSelectedResult} disabled={saving || !selectedResult}>Toevoegen</Button>
          </div>

          {catalogQuery.trim().length >= 2 && !searching ? (
            <div aria-label="Zoekresultaten samenvatting" style={{ color: '#667085' }}>
              {catalogCounts.household_article || 0} huishoudartikelen · {catalogCounts.product_type || 0} producttypen · {catalogCounts.article_group || 0} artikelgroepen
            </div>
          ) : null}

          {error ? <div role="alert" style={{ color: '#9b1c1c' }}>{error}</div> : null}
          {message ? <div role="status" style={{ color: '#1A3E2B' }}>{message}</div> : null}

          <Table dataTestId="shopping-list-table" resizableColumns tableStyle={tableStyle}>
            <colgroup>
              <col style={{ width: 76 }} />
              <col style={{ width: 190 }} />
              <col style={{ width: 150 }} />
              <col style={{ width: 180 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 224 }} />
            </colgroup>
            <thead>
              <tr className="rz-table-header">
                <th>Gekocht</th>
                <th>Artikel</th>
                <th>Artikelgroep</th>
                <th>Producttype</th>
                <th className="rz-num">Aantal</th>
                <th className="rz-num">Volume</th>
                <th>Eenheid</th>
                <th>Opmerking</th>
              </tr>
              <tr>
                <th><select className="rz-input" value={filters.checked} onChange={(event) => setFilters((current) => ({ ...current, checked: event.target.value }))} aria-label="Filter gekocht"><option value="all">Filter</option><option value="open">Nog te kopen</option><option value="checked">Gekocht</option></select></th>
                <th><input className="rz-input" value={filters.article} onChange={(event) => setFilters((current) => ({ ...current, article: event.target.value }))} placeholder="Zoeken" aria-label="Zoeken in winkellijst" /></th>
                <th><select className="rz-input" value={filters.articleGroup} onChange={(event) => setFilters((current) => ({ ...current, articleGroup: event.target.value }))} aria-label="Filter artikelgroep"><option value="">Filter</option>{articleGroupOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></th>
                <th><select className="rz-input" value={filters.productType} onChange={(event) => setFilters((current) => ({ ...current, productType: event.target.value }))} aria-label="Filter producttype"><option value="">Filter</option>{productTypeOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></th>
                <th>&nbsp;</th><th>&nbsp;</th>
                <th><select className="rz-input" value={filters.unit} onChange={(event) => setFilters((current) => ({ ...current, unit: event.target.value }))} aria-label="Filter eenheid">{UNITS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></th>
                <th>&nbsp;</th>
              </tr>
            </thead>
            <tbody>
              {loading ? <tr><td colSpan={8}>Winkellijst laden…</td></tr> : visibleItems.length === 0 ? <><tr><td colSpan={8}>Nog geen artikelen op de winkellijst.</td></tr><tr><td colSpan={8}>&nbsp;</td></tr><tr><td colSpan={8}>&nbsp;</td></tr></> : visibleItems.map((item) => (
                <tr key={item.id}>
                  <td><input type="checkbox" checked={Boolean(item.checked)} onChange={(event) => updateChecked(item, event.target.checked)} aria-label={`Gekocht ${item.article_name}`} style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} /></td>
                  <td title={item.article_name}>{item.article_name}</td>
                  <td title={item.article_group_name}>{item.article_group_name}</td>
                  <td title={item.product_type_name}>{item.product_type_name}</td>
                  <td><input className="rz-input rz-num" style={inlineInputStyle} defaultValue={item.quantity ?? ''} inputMode="decimal" aria-label={`Aantal ${item.article_name}`} onBlur={(event) => updateItem(item, { quantity: event.target.value || null })} /></td>
                  <td><input className="rz-input rz-num" style={inlineInputStyle} defaultValue={item.volume ?? ''} inputMode="decimal" aria-label={`Volume ${item.article_name}`} onBlur={(event) => updateItem(item, { volume: event.target.value || null })} /></td>
                  <td><select className="rz-input" style={inlineInputStyle} value={item.unit || ''} aria-label={`Eenheid ${item.article_name}`} onChange={(event) => updateItem(item, { unit: event.target.value })}>{UNITS.map(([value, label]) => <option key={value} value={value}>{value ? label : 'Geen'}</option>)}</select></td>
                  <td><input className="rz-input" style={inlineInputStyle} defaultValue={item.note || ''} aria-label={`Opmerking ${item.article_name}`} onBlur={(event) => updateItem(item, { note: event.target.value })} /></td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Button type="button" onClick={completeShopping} disabled={saving || Number(list.item_count || 0) === 0}>Winkelen afgerond</Button></div>
        </div>
      </Card>
    </AppShell>
  )
}
