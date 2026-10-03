import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../../ui/Button'
import CatalogProductImage from './CatalogProductImage'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import Select from '../../ui/Select.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './mobileCatalog.css'

const PAGE_SIZE = 10

function text(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function kindLabel(value) {
  return String(value ?? '').trim().toLowerCase() === 'exact' ? 'Exact product' : 'Generiek'
}

export default function MobileCatalogPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('')
  const [sort, setSort] = useState('name-asc')
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setIsLoading(true)
      setError('')
      try {
        const [sortBy, direction] = sort === 'name-desc' ? ['name', 'desc'] : ['name', 'asc']
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String((page - 1) * PAGE_SIZE),
          sort_by: sortBy,
          sort_direction: direction,
        })
        if (query.trim()) params.set('name', query.trim())
        if (kind) params.set('catalog_kind', kind)
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
  }, [kind, page, query, sort])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const summary = isLoading ? 'Catalogus laden…' : `${total} artikelen`
  const hasFilters = Boolean(query || kind)

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  const kindOptions = useMemo(() => [
    { value: '', label: 'Alle soorten' },
    { value: 'generic', label: 'Generiek' },
    { value: 'exact', label: 'Exact product' },
  ], [])

  function resetFilters() {
    setQuery('')
    setKind('')
    setPage(1)
  }

  return (
    <div className="rz-screen rz-mobile-catalog-screen" data-testid="mobile-catalog-page">
      <MobileModuleHeader title="Catalogus" testId="mobile-catalog-header" />
      <main className="rz-mobile-catalog-content">
        <section className="rz-mobile-catalog-toolbar" aria-label="Catalogus zoeken en filteren">
          <label className="rz-mobile-catalog-search">
            <span className="rz-mobile-catalog-visually-hidden">Zoek</span>
            <input
              className="rz-input"
              type="search"
              value={query}
              onChange={(event) => { setQuery(event.target.value); setPage(1) }}
              placeholder="Zoek artikel"
              autoComplete="off"
            />
          </label>
          <div className="rz-mobile-catalog-filters">
            <div>
              <span id="mobile-catalog-kind-label" className="rz-mobile-catalog-visually-hidden">Soort</span>
              <Select
                ariaLabelledby="mobile-catalog-kind-label"
                value={kind}
                onChange={(value) => { setKind(value); setPage(1) }}
                triggerClassName="rz-mobile-catalog-select"
                options={kindOptions}
              />
            </div>
            <div>
              <span id="mobile-catalog-sort-label" className="rz-mobile-catalog-visually-hidden">Sorteren</span>
              <Select
                ariaLabelledby="mobile-catalog-sort-label"
                value={sort}
                onChange={(value) => { setSort(value); setPage(1) }}
                triggerClassName="rz-mobile-catalog-select"
                options={[
                  { value: 'name-asc', label: 'Naam A–Z' },
                  { value: 'name-desc', label: 'Naam Z–A' },
                ]}
              />
            </div>
          </div>
          {hasFilters ? <Button type="button" variant="secondary" className="rz-mobile-catalog-clear" onClick={resetFilters}>Filters wissen</Button> : null}
        </section>

        <div className="rz-mobile-catalog-summary" aria-live="polite">{summary}</div>

        {error ? <section className="rz-mobile-catalog-state" role="alert">{error}</section> : null}
        {!error && !isLoading && items.length === 0 ? <section className="rz-mobile-catalog-state">Geen catalogusartikelen gevonden.</section> : null}

        {!error && items.length > 0 ? (
          <section className="rz-mobile-catalog-list" aria-label="Catalogusartikelen">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className="rz-mobile-catalog-row"
                onClick={() => navigate(`/catalogus/${encodeURIComponent(item.id)}`)}
                data-testid={`mobile-catalog-open-${item.id}`}
              >
                <CatalogProductImage imageUrl={item.image_url} productName={item.name} compact />
                <span className="rz-mobile-catalog-row-main">
                  <strong>{text(item.name)}</strong>
                  <span>{[kindLabel(item.catalog_kind), text(item.brand, '')].filter(Boolean).join(' • ')}</span>
                  <span>{text(item.product_type, 'Geen producttype')}</span>
                  <span>GPC-familie: {text(item.gpc_family_name, 'Niet geclassificeerd')}</span>
                </span>

              </button>
            ))}
          </section>
        ) : null}

        {!error && total > PAGE_SIZE ? (
          <nav className="rz-mobile-catalog-pagination" aria-label="Paginering Catalogus">
            <Button type="button" variant="secondary" disabled={currentPage <= 1 || isLoading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Vorige</Button>
            <span>Pagina {currentPage} van {pageCount}</span>
            <Button type="button" variant="secondary" disabled={currentPage >= pageCount || isLoading} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>Volgende</Button>
          </nav>
        ) : null}
      </main>
    </div>
  )
}
