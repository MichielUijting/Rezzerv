import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import '../externalDatabases/externalDatabases.css'
import './catalog.css'

const PAGE_SIZE = 10

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function qualityClass(status) {
  if (status === 'Compleet') return 'rz-catalog-status rz-catalog-status--complete'
  if (status === 'Conflict') return 'rz-catalog-status rz-catalog-status--conflict'
  return 'rz-catalog-status rz-catalog-status--review'
}

function csvValue(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export default function CatalogPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [filters, setFilters] = useState({
    name: '',
    brand: '',
    primaryGtin: '',
    productType: '',
    source: '',
    householdArticleCount: '',
    qualityStatus: '',
  })
  const [sort, setSort] = useState({ key: 'name', direction: 'asc' })
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setIsLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth('/api/catalog?limit=2000', { method: 'GET' })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Catalogus kon niet worden geladen')
        if (!cancelled) setItems(Array.isArray(data?.items) ? data.items : [])
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Catalogus kon niet worden geladen')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadCatalog()
    return () => { cancelled = true }
  }, [])

  const filteredItems = useMemo(() => {
    const normalizedFilters = Object.fromEntries(
      Object.entries(filters).map(([key, value]) => [key, String(value || '').trim().toLowerCase()])
    )

    const rows = items.filter((item) => {
      return (!normalizedFilters.name || String(item.name || '').toLowerCase().includes(normalizedFilters.name))
        && (!normalizedFilters.brand || String(item.brand || '').toLowerCase().includes(normalizedFilters.brand))
        && (!normalizedFilters.primaryGtin || String(item.primary_gtin || '').toLowerCase().includes(normalizedFilters.primaryGtin))
        && (!normalizedFilters.productType || String(item.product_type || '').toLowerCase().includes(normalizedFilters.productType))
        && (!normalizedFilters.source || String(item.source || '').toLowerCase().includes(normalizedFilters.source))
        && (!normalizedFilters.householdArticleCount || String(item.household_article_count ?? '').toLowerCase().includes(normalizedFilters.householdArticleCount))
        && (!normalizedFilters.qualityStatus || String(item.quality_status || '').toLowerCase() === normalizedFilters.qualityStatus)
    })

    rows.sort((left, right) => {
      const a = String(left?.[sort.key] ?? '').toLowerCase()
      const b = String(right?.[sort.key] ?? '').toLowerCase()
      const result = a.localeCompare(b, 'nl')
      return sort.direction === 'desc' ? -result : result
    })

    return rows
  }, [items, filters, sort])

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => items.some((item) => item.id === id)))
  }, [items])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const visibleIds = visibleItems.map((item) => item.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id))

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

  function toggleSelected(id) {
    setSelectedIds((current) => current.includes(id)
      ? current.filter((selectedId) => selectedId !== id)
      : [...current, id])
  }

  function toggleVisible() {
    setSelectedIds((current) => {
      if (allVisibleSelected) return current.filter((id) => !visibleIds.includes(id))
      return Array.from(new Set([...current, ...visibleIds]))
    })
  }

  function clearSelection() {
    setSelectedIds([])
    setMessage('Selectie gewist.')
  }

  function exportSelected() {
    const selectedItems = items.filter((item) => selectedIds.includes(item.id))
    if (!selectedItems.length) {
      setMessage('Selecteer eerst een of meer catalogusartikelen.')
      return
    }

    const rows = [
      ['Universeel artikel', 'Merk', 'Primaire GTIN', 'Producttype', 'Bron', 'Huishoudartikelen', 'Status'],
      ...selectedItems.map((item) => [
        item.name,
        item.brand,
        item.primary_gtin,
        item.product_type,
        item.source,
        item.household_article_count,
        item.quality_status,
      ]),
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
                <p>Read-only overzicht van universele artikelen, Producttypen en centrale productidentiteiten.</p>
              </div>
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
            {message ? <div className="rz-inline-feedback">{message}</div> : null}

            <div className="rz-external-databases-actions" aria-label="Bulkacties Catalogus">
              <Button type="button" variant="secondary" disabled={!selectedIds.length} onClick={exportSelected}>
                Exporteren
              </Button>
              <Button type="button" variant="secondary" disabled={!selectedIds.length} onClick={clearSelection}>
                Selectie wissen
              </Button>
              <span className="rz-external-databases-muted">Geselecteerd: {selectedIds.length}</span>
            </div>

            <div className="rz-table-scroll rz-table-scroll--wide">
              <Table dataTestId="catalog-table" tableClassName="rz-catalog-table" resizableColumns>
                <colgroup>
                  <col className="rz-catalog-col-select" />
                  <col className="rz-catalog-col-name" />
                  <col className="rz-catalog-col-brand" />
                  <col className="rz-catalog-col-gtin" />
                  <col className="rz-catalog-col-product-type" />
                  <col className="rz-catalog-col-source" />
                  <col className="rz-catalog-col-household-count" />
                  <col className="rz-catalog-col-status" />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th className="rz-check">
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleVisible}
                        aria-label="Selecteer alle zichtbare catalogusartikelen"
                      />
                    </th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('name')}>Universeel artikel <span>{sortMark('name')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('brand')}>Merk <span>{sortMark('brand')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('primary_gtin')}>Primaire GTIN <span>{sortMark('primary_gtin')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('product_type')}>Producttype <span>{sortMark('product_type')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('source')}>Bron <span>{sortMark('source')}</span></button></th>
                    <th className="rz-num"><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('household_article_count')}>Huishoudartikelen <span>{sortMark('household_article_count')}</span></button></th>
                    <th><button type="button" className="rz-external-databases-sort" onClick={() => updateSort('quality_status')}>Status <span>{sortMark('quality_status')}</span></button></th>
                  </tr>
                  <tr className="rz-external-databases-filter-row">
                    <th />
                    <th><input className="rz-table-filter" placeholder="Zoek" value={filters.name} onChange={(event) => updateFilter('name', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.brand} onChange={(event) => updateFilter('brand', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.primaryGtin} onChange={(event) => updateFilter('primaryGtin', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.productType} onChange={(event) => updateFilter('productType', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.source} onChange={(event) => updateFilter('source', event.target.value)} /></th>
                    <th><input className="rz-table-filter" placeholder="Filter" value={filters.householdArticleCount} onChange={(event) => updateFilter('householdArticleCount', event.target.value)} /></th>
                    <th>
                      <select className="rz-table-filter" value={filters.qualityStatus} onChange={(event) => updateFilter('qualityStatus', event.target.value)} aria-label="Kwaliteitsstatus filter">
                        <option value="">Alle</option>
                        <option value="compleet">Compleet</option>
                        <option value="controle nodig">Controle nodig</option>
                        <option value="conflict">Conflict</option>
                      </select>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan="8">Catalogus laden...</td></tr>
                  ) : visibleItems.length ? visibleItems.map((item) => (
                    <tr key={item.id} onDoubleClick={() => navigate(`/catalogus/${encodeURIComponent(item.id)}`)} data-testid={`catalog-row-${item.id}`}>
                      <td className="rz-check">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelected(item.id)}
                          aria-label={`Selecteer ${text(item.name, 'catalogusartikel')}`}
                        />
                      </td>
                      <td>{text(item.name)}</td>
                      <td>{text(item.brand)}</td>
                      <td>{text(item.primary_gtin)}</td>
                      <td>{text(item.product_type)}</td>
                      <td>{text(item.source)}</td>
                      <td className="rz-num">{Number(item.household_article_count || 0)}</td>
                      <td><span className={qualityClass(item.quality_status)}>{text(item.quality_status)}</span></td>
                    </tr>
                  )) : (
                    <tr><td colSpan="8">Geen universele artikelen gevonden.</td></tr>
                  )}
                </tbody>
              </Table>
            </div>

            <div className="rz-external-databases-pagination" aria-label="Paginering Catalogus">
              <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(1)}>Eerste</Button>
              <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>Vorige</Button>
              <span className="rz-external-databases-page-indicator">Pagina {currentPage} van {pageCount}</span>
              <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>Volgende</Button>
              <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => goToPage(pageCount)}>Laatste</Button>
              <span className="rz-external-databases-muted">{filteredItems.length} artikelen</span>
            </div>
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
