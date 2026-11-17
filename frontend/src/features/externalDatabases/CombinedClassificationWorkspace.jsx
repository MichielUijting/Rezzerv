import { useCallback, useEffect, useMemo, useState } from 'react'
import ClassificationImportPanel from './ClassificationImportPanel'
import CatalogGpcActionPage from '../catalog/CatalogGpcActionPage'
import CbsClassificationPage from '../catalog/CbsClassificationPage'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

const PAGE_SIZE = 100

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

// Read-only working-list export; intentionally NOT the 23-column import format.
const EXPORT_FIELDS = [
  ['id', 'product_id'],
  ['name', 'Artikel'],
  ['brand', 'Merk'],
  ['gtin', 'Barcode'],
  ['gpc_code', 'GS1 GPC code'],
  ['cbs_code', 'CBS ECOICOPv2 code'],
  ['cbs_name', 'CBS omschrijving'],
  ['cbs_reference_version', 'CBS referentieversie'],
  ['gpc_status', 'GS1 status'],
  ['cbs_status', 'CBS status'],
]

function csvField(value) {
  let result = String(value ?? '')
  if (/^\s*[=+@-]/.test(result)) result = "'" + result
  return '"' + result.replace(/"/g, '""') + '"'
}

export default function CombinedClassificationWorkspace({ initialProductId = '' }) {
  const [products, setProducts] = useState([])
  const [selectedId, setSelectedId] = useState(initialProductId)
  const [selectedIds, setSelectedIds] = useState([])
  const [filteredTableRows, setFilteredTableRows] = useState([])
  const [pageRows, setPageRows] = useState([])
  const [taskCount, setTaskCount] = useState(null)
  const [productTotal, setProductTotal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const { showFeedback } = useAppFeedback()
  useEffect(() => { if (error) showFeedback({ variant: 'error', message: error }) }, [error, showFeedback])
  const mayUpdateGpc = canCurrentUserPerform('gpc.update', readStoredAuthContext())
  const selected = useMemo(() => loading || error ? null
    : products.find((item) => item.id === selectedId) || null,
  [products, selectedId, loading, error])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setProducts([])
      setError('')
      setTaskCount(null)
      setProductTotal(null)
      try {
        const items = []
        let total = 0
        let previewCommitted = false
        do {
          const response = await fetchJsonWithAuth(
            `/api/cbs-classifications/workqueue?limit=${PAGE_SIZE}&offset=${items.length}`,
            { signal: controller.signal },
          )
          const data = await response.json().catch(() => ({}))
          if (!response.ok || !Array.isArray(data.items)) throw new Error('Catalogusartikelen konden niet worden geladen.')
          if (!items.length) {
            total = Number(data.total)
            setProductTotal(total)
          }
          if (data.task_count_scope !== 'page' || !Array.isArray(data.tasks)) {
            throw new Error('De unieke classificatiewerkvoorraad is niet beschikbaar.')
          }
          // Tasks are unique by canonical product ID plus official system.
          if (new Set(data.tasks.map((task) => task.key)).size !== data.tasks.length) {
            throw new Error('De werkvoorraad bevat dubbele classificatietaken.')
          }
          setTaskCount((previous) => (previous ?? 0) + data.tasks.length)
          if (!Number.isSafeInteger(total) || total < 0 || Number(data.total) !== total ||
              (!data.items.length && total > items.length)) {
            throw new Error('De artikellijst is tijdens het ophalen veranderd. Open Classificeren opnieuw.')
          }
          const currentIds = new Set(items.map((item) => item.id))
          const incomingIds = data.items.map((item) => item.id)
          if (incomingIds.some((id) => !id || currentIds.has(id)) ||
              new Set(incomingIds).size !== incomingIds.length) {
            throw new Error('De werkvoorraad bevat dubbele of ongeldige Catalogusidentiteiten.')
          }
          items.push(...data.items)
          // Render the first eight articles as soon as the first validated
          // 100-product response arrives. Until all batches are verified the
          // table is read-only and no global counts/filters are final.
          if (!previewCommitted && items.length > 0 && !controller.signal.aborted) {
            previewCommitted = true
            setProducts(items.slice(0, 8))
          }
        } while (items.length < total)
        if (!controller.signal.aborted) {
          setProducts(items)
          const liveIds = new Set(items.map((item) => item.id))
          setSelectedIds((previous) => previous.filter((id) => liveIds.has(id)))
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          // Partial data is never presented as a verified complete worklist.
          setProducts([])
          setError(err.message || 'Artikelen niet beschikbaar.')
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [revision])

  // Keep the standard DataTable as the authority for sort, filter and paging.
  const onFilteredRowsChange = useCallback((items) => {
    setFilteredTableRows((previous) => (
      previous.length === items.length && previous.every((row, i) => row.id === items[i].id)
        ? previous : items
    ))
  }, [])
  const onPageRowsChange = useCallback((items) => {
    setPageRows((previous) => (
      previous.length === items.length && previous.every((row, i) => row.id === items[i].id)
        ? previous : items
    ))
  }, [])
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const visibleIds = useMemo(() => new Set(products.map((item) => item.id)), [products])
  const pageIds = pageRows.map((row) => row.id).filter((id) => visibleIds.has(id))
  const filteredIds = filteredTableRows.map((row) => row.id).filter((id) => visibleIds.has(id))
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id))
  const allTableSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedSet.has(id))

  const toggleIds = useCallback((ids, checked) => {
    setSelectedIds((previous) => {
      const next = new Set(previous)
      for (const id of ids) {
        if (checked) next.add(id)
        else next.delete(id)
      }
      return [...next]
    })
  }, [])
  const togglePage = useCallback(() => toggleIds(pageIds, !allPageSelected),
    [toggleIds, pageIds, allPageSelected])
  const toggleTable = useCallback(() => toggleIds(filteredIds, !allTableSelected),
    [toggleIds, filteredIds, allTableSelected])

  const tableColumns = useMemo(() => [
    { ...columns[0], renderFilter: () => <input type="checkbox"
      aria-label="Alle rijen op deze pagina" title="Alle rijen op deze pagina"
      data-testid="classification-workqueue-select-all-page"
      checked={allPageSelected} disabled={loading || !pageIds.length}
      onChange={togglePage} /> },
    ...columns.slice(1),
  ], [allPageSelected, loading, pageIds.length, togglePage])

  function exportSelection() {
    if (loading || error || !selectedIds.length) return
    const ordered = [
      ...filteredTableRows.filter((item) => selectedSet.has(item.id)),
      ...products.filter((item) => selectedSet.has(item.id) &&
        !filteredTableRows.some((visible) => visible.id === item.id)),
    ]
    if (!ordered.length) return
    const rows = [
      EXPORT_FIELDS.map(([, label]) => label),
      ...ordered.map((item) => EXPORT_FIELDS.map(([field]) => (
        field === 'gpc_status' || field === 'cbs_status'
          ? (item[field] === 'classified' ? 'Geclassificeerd' : 'Niet geclassificeerd')
          : item[field]
      ))),
    ]
    const csv = rows.map((cells) => cells.map(csvField).join(';')).join('\r\n') + '\r\n'
    const url = URL.createObjectURL(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'Inhuis_Artikelclassificeren_Geselecteerde_artikelen.csv'
    document.body.appendChild(anchor)
    try { anchor.click() } finally {
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
    showFeedback({ variant: 'success',
      message: `${ordered.length} geselecteerde Catalogusartikelen geëxporteerd. Geen classificaties gewijzigd.` })
  }

  return <section aria-label="GS1 en CBS classificeren" data-testid="combined-classification-workspace">
    <h3>Artikel classificeren</h3>
    <ClassificationImportPanel onApplied={() => setRevision((value) => value + 1)} />
    <p>Deze tabel toont alle centrale Catalogusartikelen. Een open classificatietaak betekent een ontbrekende GS1- of CBS-code, niet noodzakelijk een mislukte import. Kies één artikel om beide classificaties te beoordelen of selecteer rijen om te exporteren.</p>
    {!loading && !error && productTotal !== null && taskCount !== null
      ? <p role="status" data-testid="classification-workqueue-counts">
        {productTotal} unieke Catalogusartikelen · {taskCount} open classificatietaken
        (afzonderlijk geteld voor GS1 en CBS).
      </p> : null}
    <div className="rz-classification-workqueue-select-actions">
      <span role="status" data-testid="classification-workqueue-selected-count">
        {selectedIds.length} rijen geselecteerd
      </span>
      <label className="rz-classification-import-select-all">
        <input type="checkbox" checked={allTableSelected}
          disabled={loading || Boolean(error) || !filteredIds.length}
          onChange={toggleTable} aria-label="Alle rijen in de tabel"
          data-testid="classification-workqueue-select-all-table" />
        <span>Alle rijen in de tabel</span>
      </label>
    </div>

    {loading && products.length > 0 ? <p role="status" data-testid="classification-first-page-preview">
      De eerste acht artikelen zijn alvast zichtbaar. Inhuis controleert nog de volledige
      werkvoorraad; zoeken, selecteren en bewerken worden pas beschikbaar na afronding.
    </p> : null}
    <fieldset disabled={loading || Boolean(error)} aria-busy={loading}
      style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
    <DataTable
      dataTestId="combined-classification-articles"
      columns={tableColumns} data={error ? [] : loading ? products.slice(0, 8) : products}
      pageReady={!loading}
      getRowKey={(item) => item.id}
      pageSize={8}
      onFilteredRowsChange={onFilteredRowsChange}
      onPageRowsChange={onPageRowsChange}
      paginationActions={<>
        <Button type="button" variant="secondary" disabled={loading || !selectedIds.length}
          onClick={() => setSelectedIds([])} data-testid="classification-workqueue-clear">
          Selectie wissen
        </Button>
        <Button type="button" variant="secondary" disabled={loading || Boolean(error) || !selectedIds.length}
          onClick={exportSelection} data-testid="classification-workqueue-export">
          Geselecteerde rijen exporteren ({selectedIds.length})
        </Button>
      </>}
      emptyMessage={loading ? 'Catalogusartikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen Catalogusartikelen.'}
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
            checked={selectedSet.has(item.id)} disabled={loading}
            onChange={(event) => toggleIds([item.id], event.target.checked)} />
        </td>
        {columns.slice(1).map((column) => <td key={column.key}>
          {typeof column.renderCell === 'function' ? column.renderCell(item) : item[column.key]}
        </td>)}
      </tr>}
    />
    </fieldset>
    {selected ? <div className="rz-classification-detail" data-testid="combined-selected-article">
      <div className="rz-classification-selected-heading">
        <strong>{selected.name}{selected.brand ? ' · ' + selected.brand : ''}</strong>
        <span>Barcode: {selected.gtin || 'Niet vastgelegd'}</span>
      </div>
      <div className="rz-classification-dual-grid" data-testid="classification-dual-panels">
        <div className="rz-classification-dual-panel" aria-label="GS1 GPC-classificatie" data-testid="classification-gs1-panel">
          {!mayUpdateGpc ? <p role="status">GS1 alleen lezen: onvoldoende wijzigingsrechten.</p> : null}
          <CatalogGpcActionPage key={selected.id} embedded readOnly={!mayUpdateGpc}
            onSaved={() => setRevision((value) => value + 1)}
            selectedProduct={{ id: selected.id, name: selected.name, brand: selected.brand,
              primary_gtin: selected.gtin }} />
        </div>
        <div className="rz-classification-dual-panel" aria-label="CBS ECOICOPv2-classificatie" data-testid="classification-cbs-panel">
          <CbsClassificationPage key={selected.id + '-cbs'} embedded productId={selected.id}
            onSaved={() => setRevision((value) => value + 1)} />
        </div>
      </div>
    </div> : <p role="status">Selecteer een artikel in de tabel om beide classificaties naast elkaar te bekijken.</p>}
  </section>
}
