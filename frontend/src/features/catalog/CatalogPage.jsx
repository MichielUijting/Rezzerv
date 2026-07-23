import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
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

export default function CatalogPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [filters, setFilters] = useState({ search: '', productType: '', quality: '' })
  const [sort, setSort] = useState({ key: 'name', direction: 'asc' })
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

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
    const search = filters.search.trim().toLowerCase()
    const productType = filters.productType.trim().toLowerCase()
    const quality = filters.quality.trim().toLowerCase()
    const rows = items.filter((item) => {
      const searchable = [item.name, item.brand, item.primary_gtin, item.product_type].join(' ').toLowerCase()
      return (!search || searchable.includes(search))
        && (!productType || String(item.product_type || '').toLowerCase().includes(productType))
        && (!quality || String(item.quality_status || '').toLowerCase() === quality)
    })
    rows.sort((left, right) => {
      const a = String(left?.[sort.key] ?? '').toLowerCase()
      const b = String(right?.[sort.key] ?? '').toLowerCase()
      const result = a.localeCompare(b, 'nl')
      return sort.direction === 'desc' ? -result : result
    })
    return rows
  }, [items, filters, sort])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function updateSort(key) {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
      : { key, direction: 'asc' })
  }

  return (
    <AppShell title="Catalogus" showExit={false}>
      <div className="rz-catalog-page" data-testid="catalog-page">
        <ScreenCard fullWidth>
          <div className="rz-catalog-header">
            <div>
              <h2>Catalogus</h2>
              <p>Read-only overzicht van universele artikelen, Producttypen en centrale productidentiteiten.</p>
            </div>
          </div>

          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

          <div className="rz-catalog-table-frame">
            <Table dataTestId="catalog-table" tableClassName="rz-catalog-table" resizableColumns>
              <colgroup>
                <col className="rz-catalog-col-name" />
                <col className="rz-catalog-col-brand" />
                <col className="rz-catalog-col-gtin" />
                <col className="rz-catalog-col-product-type" />
                <col className="rz-catalog-col-source" />
                <col className="rz-catalog-col-household-count" />
                <col className="rz-catalog-col-status" />
              </colgroup>
              <thead>
                <tr className="rz-table-filters">
                  <th><input className="rz-input rz-inline-input" placeholder="Zoek" value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} /></th>
                  <th />
                  <th />
                  <th><input className="rz-input rz-inline-input" placeholder="Filter" value={filters.productType} onChange={(event) => updateFilter('productType', event.target.value)} /></th>
                  <th />
                  <th />
                  <th>
                    <select className="rz-input rz-inline-input" value={filters.quality} onChange={(event) => updateFilter('quality', event.target.value)}>
                      <option value="">Filter</option>
                      <option value="compleet">Compleet</option>
                      <option value="controle nodig">Controle nodig</option>
                      <option value="conflict">Conflict</option>
                    </select>
                  </th>
                </tr>
                <tr className="rz-table-header">
                  <th onClick={() => updateSort('name')}>Universeel artikel</th>
                  <th onClick={() => updateSort('brand')}>Merk</th>
                  <th onClick={() => updateSort('primary_gtin')}>Primaire GTIN</th>
                  <th onClick={() => updateSort('product_type')}>Producttype</th>
                  <th onClick={() => updateSort('source')}>Bron</th>
                  <th className="rz-num" onClick={() => updateSort('household_article_count')}>Huishoudartikelen</th>
                  <th onClick={() => updateSort('quality_status')}>Status</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan="7">Catalogus laden...</td></tr>
                ) : visibleItems.length ? visibleItems.map((item) => (
                  <tr key={item.id} onDoubleClick={() => navigate(`/catalogus/${encodeURIComponent(item.id)}`)} data-testid={`catalog-row-${item.id}`}>
                    <td>{text(item.name)}</td>
                    <td>{text(item.brand)}</td>
                    <td>{text(item.primary_gtin)}</td>
                    <td>{text(item.product_type)}</td>
                    <td>{text(item.source)}</td>
                    <td className="rz-num">{Number(item.household_article_count || 0)}</td>
                    <td><span className={qualityClass(item.quality_status)}>{text(item.quality_status)}</span></td>
                  </tr>
                )) : (
                  <tr><td colSpan="7">Geen universele artikelen gevonden.</td></tr>
                )}
              </tbody>
            </Table>
          </div>

          <div className="rz-catalog-pagination">
            <Button type="button" variant="secondary" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Vorige</Button>
            <span>Pagina {currentPage} van {pageCount} - {filteredItems.length} artikelen</span>
            <Button type="button" variant="secondary" disabled={currentPage >= pageCount} onClick={() => setPage(currentPage + 1)}>Volgende</Button>
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
