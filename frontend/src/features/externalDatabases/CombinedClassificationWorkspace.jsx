import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ClassificationImportPanel from './ClassificationImportPanel'
import CatalogGpcActionPage from '../catalog/CatalogGpcActionPage'
import CbsClassificationPage from '../catalog/CbsClassificationPage'
import DataTable from '../../ui/DataTable'
import Pagination from '../../ui/Pagination.jsx'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

const PAGE_SIZE = 8

const columns = [
  { key: 'select', width: 60, className: 'rz-classification-workqueue-select-column' },
  { key: 'name', label: 'Artikel', width: 280, sortable: true, filterable: true,
    renderCell: (item) => item.name + (item.brand ? ' · ' + item.brand : '') },
  { key: 'gtin', label: 'Barcode', width: 160, sortable: true, filterable: true },
  { key: 'gpc_status', label: 'GS1 GPC', width: 230, sortable: true, filterable: true,
    getSortValue: (item) => item.gpc_code || 'Niet geclassificeerd',
    getFilterValue: (item) => item.gpc_code || 'Niet geclassificeerd',
    renderCell: (item) => item.gpc_code || 'Niet geclassificeerd' },
  { key: 'cbs_status', label: 'CBS ECOICOPv2', width: 260, sortable: true, filterable: true,
    getSortValue: (item) => item.cbs_code || 'Niet geclassificeerd',
    getFilterValue: (item) => item.cbs_code
      ? item.cbs_code + ' ' + item.cbs_name : 'Niet geclassificeerd',
    renderCell: (item) => item.cbs_code
      ? item.cbs_code + ' · ' + item.cbs_name : 'Niet geclassificeerd' },
]

const FILTER_KEYS = ['name', 'gtin', 'gpc_status', 'cbs_status']

function filterQuery(filters) {
  const query = new URLSearchParams()
  FILTER_KEYS.forEach((key) => {
    if (String(filters[key] || '').trim()) query.set(key, String(filters[key]).trim())
  })
  return query.toString()
}

async function fetchAllMatchingIds(filters, signal) {
  const ids = []
  const seen = new Set()
  let total = null
  while (total === null || ids.length < total) {
    const query = new URLSearchParams({ limit: '1000', offset: String(ids.length) })
    FILTER_KEYS.forEach((key) => {
      if (String(filters[key] || '').trim()) query.set(key, String(filters[key]).trim())
    })
    const response = await fetchJsonWithAuth(
      '/api/cbs-classifications/workqueue-ids?' + query, { signal },
    )
    const data = await response.json().catch(() => ({}))
    const nextTotal = Number(data.total)
    if (!response.ok || !Array.isArray(data.ids) ||
        !Number.isSafeInteger(nextTotal) || nextTotal < 0 ||
        (total !== null && total !== nextTotal) || nextTotal > 20000 ||
        (!data.ids.length && ids.length < nextTotal)) {
      throw new Error('De Catalogusselectie is veranderd of te groot. Filter eerst of probeer opnieuw.')
    }
    total = nextTotal
    for (const id of data.ids) {
      if (!id || seen.has(id)) throw new Error('Dubbele of ontbrekende Catalogusidentiteit.')
      ids.push(id)
      seen.add(id)
    }
    if (ids.length > total) throw new Error('De Catalogus is tijdens selecteren veranderd.')
  }
  return ids
}

export default function CombinedClassificationWorkspace({ initialProductId = '' }) {
  const [products, setProducts] = useState([])
  const [selectedId, setSelectedId] = useState(initialProductId)
  const [selectedIds, setSelectedIds] = useState([])
  const [filters, setFilters] = useState({})
  const [sortState, setSortState] = useState({ key: 'name', direction: 'asc' })
  const [page, setPage] = useState(1)
  const [filteredTotal, setFilteredTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [knownPageIds, setKnownPageIds] = useState(null)
  const [allFilterIds, setAllFilterIds] = useState(null)
  const [selectingAll, setSelectingAll] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const selectionAbortRef = useRef(null)
  const { showFeedback } = useAppFeedback()
  const mayUpdateGpc = canCurrentUserPerform('gpc.update', readStoredAuthContext())
  const filterKey = useMemo(() => filterQuery(filters), [filters])
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const pageIds = useMemo(() => products.map((item) => item.id), [products])
  const selected = useMemo(() => loading || error ? null :
    products.find((item) => item.id === selectedId) || null,
  [products, selectedId, loading, error])

  useEffect(() => {
    const controller = new AbortController()
    setSummary(null)
    fetchJsonWithAuth('/api/cbs-classifications/workqueue-summary', { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok || data.task_count_scope !== 'global' ||
            !Number.isSafeInteger(data.product_total) ||
            !Number.isSafeInteger(data.task_total)) {
          throw new Error('De classificatietellers zijn niet volledig.')
        }
        if (!controller.signal.aborted) setSummary(data)
      })
      .catch((err) => {
        if (!controller.signal.aborted) showFeedback({
          variant: 'warning', message: 'Globale classificatietellers zijn niet beschikbaar.',
          technicalDetail: String(err?.message || err), showTechnicalToggle: true,
          key: 'classification-count-error',
        })
      })
    return () => controller.abort()
  }, [revision, showFeedback])

  const pageQuery = useMemo(() => {
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE),
      sort: sortState.key || 'name', direction: sortState.direction || 'asc',
    })
    FILTER_KEYS.forEach((key) => {
      if (String(filters[key] || '').trim()) query.set(key, String(filters[key]).trim())
    })
    return query.toString()
  }, [page, sortState, filters])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    async function loadPage() {
      try {
        const response = await fetchJsonWithAuth(
          '/api/cbs-classifications/workqueue-page?' + pageQuery, { signal: controller.signal },
        )
        const data = await response.json().catch(() => ({}))
        const total = Number(data.total)
        if (!response.ok || !Array.isArray(data.items) ||
            data.task_count_scope !== 'page' || !Array.isArray(data.tasks) ||
            !Number.isSafeInteger(total) || total < 0 ||
            data.items.length > PAGE_SIZE ||
            data.items.some((item) => !item.id) ||
            new Set(data.items.map((item) => item.id)).size !== data.items.length ||
            new Set(data.tasks.map((task) => task.key)).size !== data.tasks.length) {
          throw new Error('De Cataloguspagina is onvolledig of ongeldig.')
        }
        if (controller.signal.aborted) return
        if (page > 1 && total > 0 && (page - 1) * PAGE_SIZE >= total) {
          setPage(Math.max(1, Math.ceil(total / PAGE_SIZE)))
          return
        }
        setProducts(data.items)
        setFilteredTotal(total)
        setKnownPageIds((current) => ({
          key: filterKey,
          ids: current?.key === filterKey
            ? [...new Set([...current.ids, ...data.items.map((item) => item.id)])]
            : data.items.map((item) => item.id),
        }))
      } catch (err) {
        if (controller.signal.aborted) return
        setProducts([])
        setFilteredTotal(0)
        setError(err?.message || 'Artikelen niet beschikbaar.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void loadPage()
    return () => controller.abort()
  }, [pageQuery, filterKey, revision])

  useEffect(() => {
    if (error) showFeedback({ variant: 'error', message: error })
  }, [error, showFeedback])
  useEffect(() => () => selectionAbortRef.current?.abort(), [])

  const updateFilter = useCallback((key, value) => {
    selectionAbortRef.current?.abort()
    setSelectingAll(false)
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
    setKnownPageIds(null)
    setAllFilterIds(null)
    setSelectedId('')
  }, [])
  const updateSort = useCallback((next) => {
    setSortState(next)
    setPage(1)
    setSelectedId('')
  }, [])
  const toggleIds = useCallback((ids, checked) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      ids.forEach((id) => { if (checked) next.add(id); else next.delete(id) })
      return [...next]
    })
  }, [])
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id))
  const knownIds = allFilterIds?.key === filterKey ? allFilterIds.ids
    : knownPageIds?.key === filterKey ? knownPageIds.ids : []
  const allTableSelected = filteredTotal > 0 && knownIds.length === filteredTotal &&
    knownIds.every((id) => selectedSet.has(id))
  const togglePage = useCallback(() => toggleIds(pageIds, !allPageSelected),
    [toggleIds, pageIds, allPageSelected])

  async function toggleTable() {
    if (loading || selectingAll || error || !filteredTotal) return
    if (allTableSelected) {
      toggleIds(knownIds, false)
      return
    }
    selectionAbortRef.current?.abort()
    const controller = new AbortController()
    selectionAbortRef.current = controller
    setSelectingAll(true)
    try {
      const ids = knownIds.length === filteredTotal ? knownIds
        : await fetchAllMatchingIds(filters, controller.signal)
      if (controller.signal.aborted) return
      if (ids.length !== filteredTotal) {
        throw new Error('De Catalogus is tijdens selecteren gewijzigd.')
      }
      setAllFilterIds({ key: filterKey, ids })
      toggleIds(ids, true)
    } catch (err) {
      if (!controller.signal.aborted) showFeedback({
        variant: 'error', message: err?.message || 'Selecteren mislukt.',
      })
    } finally {
      if (!controller.signal.aborted) setSelectingAll(false)
    }
  }

  const tableColumns = useMemo(() => [
    { ...columns[0], renderFilter: () => <input type="checkbox"
      aria-label="Alle rijen op deze pagina" title="Alle rijen op deze pagina"
      data-testid="classification-workqueue-select-all-page"
      checked={allPageSelected} disabled={loading || selectingAll || !pageIds.length}
      onChange={togglePage} /> },
    ...columns.slice(1),
  ], [allPageSelected, loading, selectingAll, pageIds.length, togglePage])

  async function exportSelection() {
    if (loading || error || exporting || !selectedIds.length) return
    setExporting(true)
    try {
      const response = await fetchJsonWithAuth(
        '/api/cbs-classifications/workqueue-selected-export', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_ids: selectedIds }),
        },
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || 'De export is mislukt.')
      }
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'Inhuis_Artikelclassificeren_Geselecteerde_artikelen.csv'
      document.body.appendChild(anchor)
      try { anchor.click() } finally {
        anchor.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
      showFeedback({ variant: 'success',
        message: selectedIds.length + ' geselecteerde Catalogusartikelen geëxporteerd. Geen classificaties gewijzigd.' })
    } catch (err) {
      showFeedback({ variant: 'error', message: err?.message || 'Export mislukt.' })
    } finally {
      setExporting(false)
    }
  }

  const pageCount = Math.max(1, Math.ceil(filteredTotal / PAGE_SIZE))
  const onClassificationSaved = () => {
    setSelectedIds([])
    setAllFilterIds(null)
    setKnownPageIds(null)
    setRevision((value) => value + 1)
  }

  return <section aria-label="GS1 en CBS classificeren" data-testid="combined-classification-workspace">
    <h3>Artikel classificeren</h3>
    <ClassificationImportPanel onApplied={onClassificationSaved} />
    <p>Deze tabel toont acht Catalogusartikelen per pagina. Zoeken, filteren en sorteren werken over de volledige Catalogus. Kies een artikel om beide classificaties te beoordelen of selecteer rijen om te exporteren.</p>
    {summary ? <p role="status" data-testid="classification-workqueue-counts">
      {summary.product_total} unieke Catalogusartikelen · {summary.task_total} open classificatietaken
      (afzonderlijk geteld voor GS1 en CBS).
    </p> : null}
    {!loading && !error ? <p role="status" data-testid="classification-first-page-ready">
      {filteredTotal} artikelen voldoen aan het huidige filter. De {products.length} zichtbare artikelen zijn direct beschikbaar.
    </p> : null}
    <div className="rz-classification-workqueue-select-actions">
      <span role="status" data-testid="classification-workqueue-selected-count">
        {selectedIds.length} rijen geselecteerd
      </span>
      <label className="rz-classification-import-select-all">
        <input type="checkbox" checked={allTableSelected}
          disabled={loading || selectingAll || Boolean(error) || !filteredTotal}
          onChange={() => { void toggleTable() }} aria-label="Alle rijen in de tabel"
          data-testid="classification-workqueue-select-all-table" />
        <span>{selectingAll ? "Selectie controleren…" : "Alle rijen in de tabel"}</span>
      </label>
    </div>

    {loading ? <p role="status" aria-live="polite">Cataloguspagina laden…</p> : null}
    <DataTable
      dataTestId="combined-classification-articles"
      columns={tableColumns} data={loading || error ? [] : products}
      serverSide
      getRowKey={(item) => item.id}
      pageSize={PAGE_SIZE} pagination={false}
      filterState={filters} onFilterChange={updateFilter}
      sortState={sortState} onSortChange={updateSort}
      paginationActions={<>
        <Button type="button" variant="secondary" disabled={!selectedIds.length || exporting}
          onClick={() => setSelectedIds([])} data-testid="classification-workqueue-clear">
          Selectie wissen
        </Button>
        <Button type="button" variant="secondary"
          disabled={loading || Boolean(error) || exporting || !selectedIds.length}
          onClick={() => { void exportSelection() }} data-testid="classification-workqueue-export">
          Geselecteerde rijen exporteren ({selectedIds.length})
        </Button>
      </>}
      emptyMessage={loading ? 'Artikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen Catalogusartikelen.'}
      renderRow={(item) => <tr key={item.id} tabIndex={0}
        aria-selected={selectedId === item.id}
        className={selectedId === item.id ? 'rz-row-selected' : ''}
        onClick={() => { if (!loading) setSelectedId(item.id) }}
        onDoubleClick={() => { if (!loading) setSelectedId(item.id) }}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return
          if (!loading && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault()
            setSelectedId(item.id)
          }
        }}>
        <td className="rz-classification-workqueue-select-cell"
          onClick={(event) => event.stopPropagation()}
          onDoubleClick={(event) => event.stopPropagation()}>
          <input type="checkbox" aria-label={`Selecteer ${item.name}`}
            checked={selectedSet.has(item.id)} disabled={loading || selectingAll}
            onChange={(event) => toggleIds([item.id], event.target.checked)} />
        </td>
        {columns.slice(1).map((column) => <td key={column.key}>
          {typeof column.renderCell === 'function' ? column.renderCell(item) : item[column.key]}
        </td>)}
      </tr>}
    />
    {!error && pageCount > 1 ? <Pagination page={page} pageCount={pageCount}
      disabled={loading || selectingAll} onPageChange={(next) => { setPage(next); setSelectedId('') }} /> : null}
    {selected ? <div className="rz-classification-detail" data-testid="combined-selected-article">
      <div className="rz-classification-selected-heading">
        <strong>{selected.name}{selected.brand ? ' · ' + selected.brand : ''}</strong>
        <span>Barcode: {selected.gtin || 'Niet vastgelegd'}</span>
      </div>
      <div className="rz-classification-dual-grid" data-testid="classification-dual-panels">
        <div className="rz-classification-dual-panel" aria-label="GS1 GPC-classificatie" data-testid="classification-gs1-panel">
          {!mayUpdateGpc ? <p role="status">GS1 alleen lezen: onvoldoende wijzigingsrechten.</p> : null}
          <CatalogGpcActionPage key={selected.id} embedded readOnly={!mayUpdateGpc}
            onSaved={onClassificationSaved}
            selectedProduct={{ id: selected.id, name: selected.name, brand: selected.brand,
              primary_gtin: selected.gtin }} />
        </div>
        <div className="rz-classification-dual-panel" aria-label="CBS ECOICOPv2-classificatie" data-testid="classification-cbs-panel">
          <CbsClassificationPage key={selected.id + '-cbs'} embedded productId={selected.id}
            onSaved={onClassificationSaved} />
        </div>
      </div>
    </div> : <p role="status">Selecteer een artikel in de tabel om beide classificaties naast elkaar te bekijken.</p>}
  </section>
}
