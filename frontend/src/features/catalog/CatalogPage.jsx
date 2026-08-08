import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import {
  canCurrentUserPerform,
  fetchJsonWithAuth,
  readStoredAuthContext,
} from '../../lib/authSession'
import '../externalDatabases/externalDatabases.css'
import './catalog.css'

const PAGE_SIZE = 10

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function sourceLabel(value) {
  const normalized = String(value ?? '').trim().toLowerCase()
  const labels = {
    receipt_user_confirmed: 'Door gebruiker bevestigd',
    receipt: 'Kassabon',
    user: 'Gebruiker',
    manual: 'Handmatig',
    openfoodfacts: 'Open Food Facts',
    open_food_facts: 'Open Food Facts',
    gs1: 'GS1',
    ai: 'AI',
    public_reference: 'Openbare referentie',
  }
  return labels[normalized] || text(value)
}

function csvValue(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export default function CatalogPage() {
  const navigate = useNavigate()
  const authContext = readStoredAuthContext()
  const canUpdateGpc = canCurrentUserPerform('gpc.update', authContext)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [selectedRows, setSelectedRows] = useState({})
  const [filters, setFilters] = useState({
    name: '', brand: '', primaryGtin: '', productType: '', source: '',
    householdArticleCount: '',
  })
  const [sort, setSort] = useState({ key: 'name', direction: 'asc' })
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setIsLoading(true)
      setError('')
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String((page - 1) * PAGE_SIZE),
          sort_by: sort.key,
          sort_direction: sort.direction,
        })
        const mappings = {
          name: 'name',
          brand: 'brand',
          primaryGtin: 'primary_gtin',
          productType: 'product_type',
          source: 'source',
          householdArticleCount: 'household_article_count',
        }
        Object.entries(mappings).forEach(([stateKey, parameter]) => {
          const value = String(filters[stateKey] || '').trim()
          if (value) params.set(parameter, value)
        })
        const response = await fetchJsonWithAuth(`/api/catalog?${params.toString()}`, { method: 'GET' })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Catalogus kon niet worden geladen')
        if (!cancelled) {
          setItems(Array.isArray(data?.items) ? data.items : [])
          setTotal(Number(data?.total || 0))
        }
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Catalogus kon niet worden geladen')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [filters, page, sort])

  const selectedIds = useMemo(() => Object.keys(selectedRows), [selectedRows])
  const visibleIds = items.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => Boolean(selectedRows[id]))
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function updateSort(key) {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
      : { key, direction: 'asc' })
    setPage(1)
  }

  function sortMark(key) {
    return sort.key === key && sort.direction === 'asc' ? '^' : 'v'
  }

  function goToPage(targetPage) {
    setPage(Math.max(1, Math.min(pageCount, targetPage)))
  }

  function toggleSelected(item) {
    setSelectedRows((current) => {
      const next = { ...current }
      if (next[item.id]) delete next[item.id]
      else next[item.id] = item
      return next
    })
  }

  function toggleVisible() {
    setSelectedRows((current) => {
      const next = { ...current }
      if (allVisibleSelected) items.forEach((item) => { delete next[item.id] })
      else items.forEach((item) => { next[item.id] = item })
      return next
    })
  }

  function clearSelection() {
    setSelectedRows({})
    setMessage('Selectie gewist.')
  }

  function exportSelected() {
    const selectedItems = Object.values(selectedRows)
    if (!selectedItems.length) {
      setMessage('Selecteer eerst een of meer catalogusartikelen.')
      return
    }
    const rows = [
      ['Universeel artikel', 'Merk', 'Primaire GTIN', 'Producttype', 'Bron', 'Huishoudartikelen'],
      ...selectedItems.map((item) => [item.name, item.brand, item.primary_gtin, item.product_type, item.source, item.household_article_count]),
    ]
    const csv = rows.map((row) => row.map(csvValue).join(';')).join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-catalogus-selectie.csv'
    link.click()
    URL.revokeObjectURL(url)
    setMessage(`Export gemaakt voor ${selectedItems.length} catalogusartikel(en).`)
  }

  return (
    <AppShell title="Catalogus" showExit={false}>
      <div className="rz-catalog-page rz-external-databases" data-testid="catalog-page">
        <ScreenCard fullWidth>
          <div className="rz-catalog-card">
            <div className="rz-catalog-header">
              <div>
                <h2>Catalogus</h2>
                <p>Overzicht van universele artikelen, centrale productidentiteiten en GS1 GPC-classificaties.</p>
              </div>
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
            {message ? <div className="rz-inline-feedback">{message}</div> : null}
            {!canUpdateGpc ? <div className="rz-inline-feedback">Alleen-lezen: jouw rol mag de catalogus bekijken, maar niet classificeren of beheren.</div> : null}

            <div className="rz-external-databases-actions" aria-label="Acties Catalogus">
              {canUpdateGpc ? <Button type="button" onClick={() => navigate('/catalogus/gpc-classificeren')}>GPC classificeren</Button> : null}
              <Button type="button" variant="secondary" disabled={!selectedIds.length} onClick={exportSelected}>Exporteren</Button>
              <Button type="button" variant="secondary" disabled={!selectedIds.length} onClick={clearSelection}>Selectie wissen</Button>
              <span className="rz-external-databases-muted">Geselecteerd: {selectedIds.length}</span>
            </div>

            <div className="rz-table-scroll rz-table-scroll--wide">
              <Table dataTestId="catalog-table" tableClassName="rz-catalog-table" resizableColumns>
                <colgroup>
                  <col className="rz-catalog-col-select" /><col className="rz-catalog-col-name" /><col className="rz-catalog-col-brand" />
                  <col className="rz-catalog-col-gtin" /><col className="rz-catalog-col-product-type" /><col className="rz-catalog-col-source" />
                  <col className="rz-catalog-col-household-count" />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th className="rz-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="Selecteer alle zichtbare catalogusartikelen" /></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('name')}>Universeel artikel <span>{sortMark('name')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('brand')}>Merk <span>{sortMark('brand')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('primary_gtin')}>Primaire GTIN <span>{sortMark('primary_gtin')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('product_type')}>Producttype <span>{sortMark('product_type')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('source')}>Bron <span>{sortMark('source')}</span></button></th>
                    <th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('household_article_count')}>Huishoudartikelen <span>{sortMark('household_article_count')}</span></button></th>
                  </tr>
                  <tr className="rz-external-databases-filter-row">
                    <th />
                    <th><input className="rz-table-filter" placeholder="Zoek" value={filters.name} onChange={(event) => updateFilter('name', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.brand} onChange={(event) => updateFilter('brand', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.primaryGtin} onChange={(event) => updateFilter('primaryGtin', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.productType} onChange={(event) => updateFilter('productType', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.source} onChange={(event) => updateFilter('source', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.householdArticleCount} onChange={(event) => updateFilter('householdArticleCount', event.target.value)} /></th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? <tr><td colSpan="7">Catalogus laden...</td></tr> : items.length ? items.map((item) => (
                    <tr key={item.id} onDoubleClick={() => navigate(`/catalogus/${encodeURIComponent(item.id)}`)} data-testid={`catalog-row-${item.id}`}>
                      <td className="rz-check"><input type="checkbox" checked={Boolean(selectedRows[item.id])} onChange={() => toggleSelected(item)} aria-label={`Selecteer ${text(item.name, 'catalogusartikel')}`} /></td>
                      <td>{text(item.name)}</td><td>{text(item.brand)}</td><td>{text(item.primary_gtin)}</td><td>{text(item.product_type)}</td>
                      <td>{sourceLabel(item.source)}</td><td className="rz-num">{Number(item.household_article_count || 0)}</td>
                    </tr>
                  )) : <tr><td colSpan="7">Geen universele artikelen gevonden.</td></tr>}
                </tbody>
              </Table>
            </div>

            <div className="rz-external-databases-pagination" aria-label="Paginering Catalogus">
              <Button type="button" variant="secondary" disabled={currentPage <= 1 || isLoading} onClick={() => goToPage(1)}>Eerste</Button>
              <Button type="button" variant="secondary" disabled={currentPage <= 1 || isLoading} onClick={() => goToPage(currentPage - 1)}>Vorige</Button>
              <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
              <Button type="button" variant="secondary" disabled={currentPage >= pageCount || isLoading} onClick={() => goToPage(currentPage + 1)}>Volgende</Button>
              <Button type="button" variant="secondary" disabled={currentPage >= pageCount || isLoading} onClick={() => goToPage(pageCount)}>Laatste</Button>
              <span className="rz-external-databases-muted">{total} artikelen</span>
            </div>
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
